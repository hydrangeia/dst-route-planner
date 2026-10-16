from __future__ import annotations

import json
import time
from pathlib import Path

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
    assert connection.inspect_live_log(None) == {
        "check_version": 1,
        "status": "disabled",
        "log_path": None,
    }
    assert connection.inspect_live_log(missing)["status"] == "missing_log"

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
    assert log.read_bytes() == waiting_bytes

    fresh_snapshot = _snapshot(world_kind="cave")
    fresh_bytes = _write_snapshot(log, fresh_snapshot)
    fresh = connection.inspect_live_log(log)
    assert fresh["check_version"] == 1
    assert fresh["status"] == "live"
    assert fresh["log_path"] == str(log)
    assert fresh["position"] == fresh_snapshot["position"]
    assert fresh["world_kind"] == "cave"
    assert fresh["sequence"] == 7
    assert fresh["age_seconds"] <= 5
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
    assert log.read_bytes() == stale_bytes

    future_snapshot = _snapshot(captured_at=time.time() + 10)
    future_bytes = _write_snapshot(log, future_snapshot)
    future = connection.inspect_live_log(log)
    assert future["status"] == "error"
    assert future["error"] == "captured_at is ahead of the local clock."
    assert "position" not in future
    assert log.read_bytes() == future_bytes


def test_inspect_live_log_reports_invalid_content_and_io_errors(tmp_path, monkeypatch) -> None:
    log = tmp_path / "client_log.txt"
    log.write_text(f"{LIVE_MARKER}{{}}\n", encoding="utf-8")
    invalid = connection.inspect_live_log(log)
    assert invalid["status"] == "error"
    assert "snapshot" in invalid["error"]

    def unreadable(path):
        raise PermissionError("permission denied")

    monkeypatch.setattr(connection, "read_latest_snapshot", unreadable)
    unreadable_result = connection.inspect_live_log(log)
    assert unreadable_result["status"] == "error"
    assert unreadable_result["error"] == "permission denied"
