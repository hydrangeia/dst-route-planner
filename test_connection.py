from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from dst_route_planner import connection
from dst_route_planner.live import LIVE_MARKER


def _snapshot(*, captured_at: float | None = None, world_kind: str = "forest") -> dict:
    return {
        "live_version": 1,
        "world_id": "private-world-id",
        "world_kind": world_kind,
        "session_id": "private-session-id",
        "sequence": 7,
        "captured_at": time.time() if captured_at is None else captured_at,
        "position": {"x": -2.5, "y": 1, "z": 8},
        "camera_heading": 270,
        "current": {"schema_version": 1, "tile_types": ["GRASS"]},
        "directions": {},
    }


def _snapshot_with_terrain(
    *, captured_at: float | None = None, anchor_clear: bool | None = True
) -> dict:
    snapshot = _snapshot(captured_at=captured_at)
    snapshot["position"] = {"x": 0, "y": 0, "z": 0}
    snapshot["landmarks"] = [
        {"prefab": "panflute", "x": 3, "z": 1},
        {"prefab": "spiderden", "x": -6, "z": 4},
    ]
    snapshot["terrain"] = {
        "tile_size": 4,
        "tiles": [
            {
                "x": 0,
                "z": 0,
                "tile": "GRASS",
                "passable": True,
                "connections": {"east": True, "north": False},
            },
            {
                "x": 4,
                "z": 0,
                "tile": "FOREST",
                "passable": True,
                "connections": {"north": False},
            },
            {
                "x": 0,
                "z": 4,
                "tile": "ROCKY",
                "passable": True,
                "connections": {"east": True},
            },
            {"x": 4, "z": 4, "tile": "MARSH", "passable": True},
            {"x": 8, "z": 0, "tile": "WATER", "passable": False},
            {"x": 8, "z": 4, "tile": "SAVANNA"},
        ],
    }
    if anchor_clear is not None:
        snapshot["player_anchor"] = {"x": 0, "z": 0, "clear": anchor_clear}
    return snapshot


def _write_snapshot(path: Path, snapshot: dict) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = f"{LIVE_MARKER}{json.dumps(snapshot, separators=(',', ':'))}\n".encode("utf-8")
    path.write_bytes(raw)
    return raw


def test_default_live_log_paths_follow_each_platform_convention(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    redirected_documents = tmp_path / "OneDrive - Player" / "Documents"
    monkeypatch.setattr(connection, "_windows_documents_directory", lambda: redirected_documents)

    assert connection.default_live_log_path(platform_name="win32", home=home) == (
        redirected_documents / "Klei" / "DoNotStarveTogether" / "client_log.txt"
    )
    assert connection.default_live_log_path(platform_name="linux", home=home) == (
        home / ".klei" / "DoNotStarveTogether" / "client_log.txt"
    )
    assert connection.default_live_log_path(platform_name="darwin", home=home) == (
        home / "Documents" / "Klei" / "DoNotStarveTogether" / "client_log.txt"
    )


def test_windows_known_folder_fallback_and_explicit_unicode_path(tmp_path, monkeypatch) -> None:
    home = tmp_path / "user profile"

    def api_unavailable():
        raise OSError("known folder unavailable")

    monkeypatch.setattr(connection, "_windows_documents_directory", api_unavailable)
    assert connection.default_live_log_path(platform_name="win32", home=home) == (
        home / "Documents" / "Klei" / "DoNotStarveTogether" / "client_log.txt"
    )

    explicit = tmp_path / "游戏 日志" / "client log.txt"
    assert connection.resolve_live_log_path(explicit) == explicit
    assert connection.resolve_live_log_path(str(explicit)) == explicit


def test_auto_alias_and_unknown_platform(tmp_path, monkeypatch) -> None:
    try:
        connection.default_live_log_path(platform_name="plan9", home=tmp_path)
    except connection.LiveLogDiscoveryError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("unsupported platforms should not guess a client-log path")

    expected = tmp_path / ".klei" / "DoNotStarveTogether" / "client_log.txt"
    monkeypatch.setattr(
        connection,
        "default_live_log_path",
        lambda: expected,
    )
    assert connection.resolve_live_log_path("auto") == expected
    assert connection.resolve_live_log_path(" AUTO ") == expected


def test_inspect_live_log_reports_statuses_without_mutating_the_log(tmp_path) -> None:
    missing = tmp_path / "missing client log.txt"
    disabled = connection.inspect_live_log(None)
    assert disabled == {
        "check_version": 1,
        "status": "disabled",
        "log_path": None,
    }
    assert "observation_summary" not in disabled
    assert "camera_heading" not in disabled
    assert "captured_at" not in disabled
    missing_result = connection.inspect_live_log(missing)
    assert missing_result["status"] == "missing_log"
    assert "observation_summary" not in missing_result
    assert "camera_heading" not in missing_result
    assert "captured_at" not in missing_result

    log = tmp_path / "DST 日志" / "client log.txt"
    log.parent.mkdir()
    log.write_text("ordinary client output\n", encoding="utf-8")
    waiting_bytes = log.read_bytes()
    waiting = connection.inspect_live_log(log)
    assert waiting == {
        "check_version": 1,
        "status": "waiting",
        "log_path": str(log),
    }
    assert "observation_summary" not in waiting
    assert "camera_heading" not in waiting
    assert "captured_at" not in waiting
    assert log.read_bytes() == waiting_bytes

    fresh_snapshot = _snapshot(world_kind="cave")
    fresh_snapshot["captured_at"] = int(time.time())
    fresh_bytes = _write_snapshot(log, fresh_snapshot)
    fresh = connection.inspect_live_log(log)
    assert fresh["check_version"] == 1
    assert fresh["status"] == "live"
    assert fresh["log_path"] == str(log)
    assert fresh["position"] == fresh_snapshot["position"]
    assert fresh["world_kind"] == "cave"
    assert fresh["sequence"] == 7
    assert fresh["camera_heading"] == fresh_snapshot["camera_heading"]
    assert fresh["captured_at"] == fresh_snapshot["captured_at"]
    assert type(fresh["camera_heading"]) is type(fresh_snapshot["camera_heading"])
    assert type(fresh["captured_at"]) is type(fresh_snapshot["captured_at"])
    assert fresh["age_seconds"] <= 5
    assert fresh["observation_summary"] == {
        "landmarks": 0,
        "terrain_available": False,
        "terrain_tiles": 0,
        "passable_tiles": 0,
        "blocked_tiles": 0,
        "unknown_tiles": 0,
        "clear_connections": 0,
        "blocked_connections": 0,
        "player_anchor": "unknown",
    }
    assert "private-world-id" not in json.dumps(fresh)
    assert "private-session-id" not in json.dumps(fresh)
    assert log.read_bytes() == fresh_bytes

    stale_snapshot = _snapshot(captured_at=time.time() - 6, world_kind="cave")
    stale_bytes = _write_snapshot(log, stale_snapshot)
    stale = connection.inspect_live_log(log)
    assert stale["status"] == "stale"
    assert stale["age_seconds"] > 5
    assert stale["world_kind"] == "cave"
    assert stale["position"] == stale_snapshot["position"]
    assert stale["camera_heading"] == stale_snapshot["camera_heading"]
    assert stale["captured_at"] == stale_snapshot["captured_at"]
    assert log.read_bytes() == stale_bytes

    future_snapshot = _snapshot(captured_at=time.time() + 10)
    future_bytes = _write_snapshot(log, future_snapshot)
    future = connection.inspect_live_log(log)
    assert future["status"] == "error"
    assert future["error"] == "captured_at is ahead of the local clock."
    assert "position" not in future
    assert "camera_heading" not in future
    assert "captured_at" not in future
    assert "observation_summary" not in future
    assert log.read_bytes() == future_bytes


def test_inspect_live_log_summarizes_only_the_validated_snapshot(tmp_path, monkeypatch) -> None:
    log = tmp_path / "client_log.txt"
    snapshot = _snapshot_with_terrain()
    raw = _write_snapshot(log, snapshot)
    snapshot_reads: list[Path] = []
    read_latest_snapshot = connection.read_latest_snapshot

    def track_snapshot_read(path):
        snapshot_reads.append(Path(path))
        return read_latest_snapshot(path)

    monkeypatch.setattr(connection, "read_latest_snapshot", track_snapshot_read)
    result = connection.inspect_live_log(log)

    assert result["status"] == "live"
    assert result["observation_summary"] == {
        "landmarks": 2,
        "terrain_available": True,
        "terrain_tiles": 6,
        "passable_tiles": 4,
        "blocked_tiles": 1,
        "unknown_tiles": 1,
        "clear_connections": 2,
        "blocked_connections": 2,
        "player_anchor": "clear",
    }
    assert snapshot_reads == [log]
    serialized = json.dumps(result)
    assert "private-world-id" not in serialized
    assert "private-session-id" not in serialized
    assert "panflute" not in serialized
    assert "spiderden" not in serialized
    assert result["camera_heading"] == snapshot["camera_heading"]
    assert result["captured_at"] == snapshot["captured_at"]
    assert log.read_bytes() == raw


@pytest.mark.parametrize(
    ("anchor_clear", "expected"),
    [(True, "clear"), (False, "blocked"), (None, "unknown")],
)
def test_inspect_live_log_reports_player_anchor_state(
    tmp_path, anchor_clear: bool | None, expected: str
) -> None:
    log = tmp_path / f"anchor-{expected}.txt"
    _write_snapshot(log, _snapshot_with_terrain(anchor_clear=anchor_clear))

    result = connection.inspect_live_log(log)

    assert result["observation_summary"]["player_anchor"] == expected


@pytest.mark.parametrize(
    ("terrain_present", "expected_available"),
    [(False, False), (True, True)],
)
def test_inspect_live_log_distinguishes_absent_and_empty_terrain(
    tmp_path, terrain_present: bool, expected_available: bool
) -> None:
    snapshot = _snapshot()
    if terrain_present:
        snapshot["terrain"] = {"tile_size": 4, "tiles": []}
    log = tmp_path / f"terrain-{expected_available}.txt"
    _write_snapshot(log, snapshot)

    summary = connection.inspect_live_log(log)["observation_summary"]

    assert summary["terrain_available"] is expected_available
    assert summary["terrain_tiles"] == 0
    assert summary["passable_tiles"] == 0
    assert summary["blocked_tiles"] == 0
    assert summary["unknown_tiles"] == 0


def test_stale_live_log_keeps_observation_summary(tmp_path) -> None:
    log = tmp_path / "stale client_log.txt"
    _write_snapshot(
        log,
        _snapshot_with_terrain(captured_at=time.time() - 6),
    )

    result = connection.inspect_live_log(log)

    assert result["status"] == "stale"
    assert result["observation_summary"]["landmarks"] == 2
    assert result["observation_summary"]["terrain_tiles"] == 6
    assert result["observation_summary"]["clear_connections"] == 2


def test_inspect_live_log_reports_invalid_content_and_io_errors(tmp_path, monkeypatch) -> None:
    log = tmp_path / "client_log.txt"
    log.write_text(f"{LIVE_MARKER}{{}}\n", encoding="utf-8")
    invalid = connection.inspect_live_log(log)
    assert invalid["status"] == "error"
    assert "snapshot" in invalid["error"]
    assert "observation_summary" not in invalid
    assert "camera_heading" not in invalid
    assert "captured_at" not in invalid

    def unreadable(path):
        raise PermissionError("permission denied")

    monkeypatch.setattr(connection, "read_latest_snapshot", unreadable)
    unreadable_result = connection.inspect_live_log(log)
    assert unreadable_result["status"] == "error"
    assert unreadable_result["error"] == "permission denied"
    assert "observation_summary" not in unreadable_result
    assert "camera_heading" not in unreadable_result
    assert "captured_at" not in unreadable_result
