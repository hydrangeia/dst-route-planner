from __future__ import annotations

import ctypes
import os
import stat
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from dst_route_planner.live import (
    FRESHNESS_SECONDS,
    LiveSnapshotError,
    age_seconds,
    read_latest_snapshot,
)


_FOLDERID_DOCUMENTS = "FDD39AD0-238F-46AF-ADB4-6C85480369C7"
_KF_FLAG_DONT_VERIFY = 0x00004000


class LiveLogDiscoveryError(OSError):
    """Raised when the current platform has no known automatic client-log path."""


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]


def _windows_documents_directory() -> Path:
    """Return the Windows Documents known folder, including user redirection."""
    if sys.platform != "win32":
        raise OSError("Windows known folders are unavailable on this platform.")

    folder = _Guid.from_buffer_copy(uuid.UUID(_FOLDERID_DOCUMENTS).bytes_le)
    folder_path = ctypes.c_wchar_p()
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    get_known_folder_path = shell32.SHGetKnownFolderPath
    get_known_folder_path.argtypes = [
        ctypes.POINTER(_Guid),
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    get_known_folder_path.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None

    result = get_known_folder_path(
        ctypes.byref(folder), _KF_FLAG_DONT_VERIFY, None, ctypes.byref(folder_path)
    )
    try:
        if result != 0 or not folder_path.value:
            raise OSError(
                f"SHGetKnownFolderPath failed with HRESULT 0x{result & 0xFFFFFFFF:08X}."
            )
        return Path(folder_path.value)
    finally:
        allocated_path = ctypes.cast(folder_path, ctypes.c_void_p)
        if allocated_path.value is not None:
            ole32.CoTaskMemFree(allocated_path)


def default_live_log_path(
    *, platform_name: str | None = None, home: Path | str | None = None
) -> Path:
    """Resolve the conventional client log location for Windows, macOS, or Linux."""
    platform_name = sys.platform if platform_name is None else platform_name

    if platform_name == "win32":
        try:
            documents = _windows_documents_directory()
        except (AttributeError, ImportError, OSError):
            # The known-folder API normally honors redirected Documents. This
            # conventional location is only a fallback if that API is unavailable.
            home_path = Path.home() if home is None else Path(home)
            documents = home_path / "Documents"
        return documents / "Klei" / "DoNotStarveTogether" / "client_log.txt"
    home_path = Path.home() if home is None else Path(home)
    if platform_name == "darwin":
        return home_path / "Documents" / "Klei" / "DoNotStarveTogether" / "client_log.txt"
    if platform_name.startswith("linux"):
        return home_path / ".klei" / "DoNotStarveTogether" / "client_log.txt"
    raise LiveLogDiscoveryError(
        f"automatic client-log discovery is unsupported on {platform_name}."
    )


def resolve_live_log_path(value: str | os.PathLike[str] | None = "auto") -> Path:
    """Resolve ``auto`` or expand a user-supplied client-log path."""
    if value is None or os.fspath(value).strip().casefold() == "auto":
        return default_live_log_path()
    return Path(value).expanduser()


def _observation_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Summarize only counts from an already validated snapshot."""
    terrain_available = "terrain" in snapshot
    tiles = snapshot["terrain"]["tiles"] if terrain_available else []
    connections = [
        connected
        for tile in tiles
        for connected in tile.get("connections", {}).values()
    ]
    anchor = snapshot.get("player_anchor")
    return {
        "landmarks": len(snapshot.get("landmarks", [])),
        "terrain_available": terrain_available,
        "terrain_tiles": len(tiles),
        "passable_tiles": sum(tile.get("passable") is True for tile in tiles),
        "blocked_tiles": sum(tile.get("passable") is False for tile in tiles),
        "unknown_tiles": sum("passable" not in tile for tile in tiles),
        "clear_connections": sum(connected is True for connected in connections),
        "blocked_connections": sum(connected is False for connected in connections),
        "player_anchor": (
            "unknown"
            if anchor is None
            else "clear"
            if anchor["clear"]
            else "blocked"
        ),
    }


def inspect_live_log(
    live_log: Path | str | None, *, now: float | None = None
) -> dict[str, Any]:
    """Read connection status without planning, recording, or changing the log."""
    if live_log is None:
        return {"check_version": 1, "status": "disabled", "log_path": None}

    path = Path(live_log)
    result: dict[str, Any] = {
        "check_version": 1,
        "status": "error",
        "log_path": str(path),
    }
    try:
        metadata = path.stat()
    except FileNotFoundError:
        result["status"] = "missing_log"
        return result
    except OSError as exc:
        result["error"] = str(exc)
        return result
    if not stat.S_ISREG(metadata.st_mode):
        result["error"] = "client log path is not a regular file."
        return result

    try:
        snapshot = read_latest_snapshot(path)
    except (LiveSnapshotError, OSError) as exc:
        result["error"] = str(exc)
        return result
    if snapshot is None:
        try:
            path.stat()
        except FileNotFoundError:
            result["status"] = "missing_log"
            return result
        except OSError as exc:
            result["error"] = str(exc)
            return result
        result["status"] = "waiting"
        return result

    try:
        age = age_seconds(snapshot, now=time.time() if now is None else now)
    except LiveSnapshotError as exc:
        result["error"] = str(exc)
        return result

    result.update(
        status="stale" if age > FRESHNESS_SECONDS else "live",
        age_seconds=age,
        position=dict(snapshot["position"]),
        world_kind=snapshot["world_kind"],
        sequence=snapshot["sequence"],
        camera_heading=snapshot["camera_heading"],
        captured_at=snapshot["captured_at"],
        observation_summary=_observation_summary(snapshot),
    )
    return result
