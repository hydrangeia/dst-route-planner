"""CLI coverage for the local interface and user-facing input errors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from dst_route_planner import app
from dst_route_planner import cli
from dst_route_planner.cli import main


def test_ui_forwards_port_browser_preference_and_live_log(monkeypatch) -> None:
    calls: list[tuple[int, bool, Path | None]] = []
    monkeypatch.setattr(
        app,
        "run_app",
        lambda *, port, open_browser, live_log: calls.append((port, open_browser, live_log)),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["route_planner.py", "--ui", "--port", "8042", "--no-browser", "--live-log", "client.log"],
    )

    assert main() == 0
    assert calls == [(8042, False, Path("client.log"))]


def test_ui_uses_automatic_log_discovery_by_default(monkeypatch) -> None:
    selected_log = Path("redirected Documents") / "Klei" / "client_log.txt"
    calls: list[Path] = []
    resolver_calls = []

    def resolve(value):
        resolver_calls.append(value)
        return selected_log

    monkeypatch.setattr(cli, "resolve_live_log_path", resolve)
    monkeypatch.setattr(
        app,
        "run_app",
        lambda *, port, open_browser, live_log: calls.append(live_log),
    )
    monkeypatch.setattr(sys, "argv", ["route_planner.py", "--ui", "--no-browser"])

    assert main() == 0
    assert calls == [selected_log]
    assert resolver_calls == [Path("auto")]


@pytest.mark.parametrize(
    ("status", "exit_code"),
    [
        ("live", 0),
        ("stale", 1),
        ("missing_log", 1),
        ("waiting", 1),
        ("disabled", 1),
        ("error", 2),
    ],
)
def test_check_live_status_messages_and_exit_codes(
    monkeypatch, capsys, status: str, exit_code: int
) -> None:
    selected_log = Path("日志 folder") / "client log.txt"
    response = {
        "check_version": 1,
        "status": status,
        "log_path": None if status == "disabled" else str(selected_log),
        "error": "invalid latest collector line" if status == "error" else None,
        # The reporter should never print these identifiers, even if a caller
        # accidentally supplies them.
        "world_id": "private-world-id",
        "session_id": "private-session-id",
    }
    if status in {"live", "stale"}:
        response.update(
            age_seconds=0.2 if status == "live" else 8.0,
            position={"x": -4, "y": 1.5, "z": 12},
            world_kind="cave",
            sequence=9,
        )
    monkeypatch.setattr(cli, "resolve_live_log_path", lambda value: selected_log)
    monkeypatch.setattr(cli, "inspect_live_log", lambda path: response)
    monkeypatch.setattr(sys, "argv", ["route_planner.py", "--check-live"])

    assert main() == exit_code
    output = capsys.readouterr().out
    assert ("(disabled)" if status == "disabled" else str(selected_log)) in output
    assert "private-world-id" not in output
    assert "private-session-id" not in output
    if status in {"live", "stale"}:
        assert "age" in output
        assert "x=-4" in output
        assert "z=12" in output
        assert "cave" in output
    if status == "waiting":
        assert "no collector snapshot" in output
    if status == "missing_log":
        assert "not found" in output
    if status == "error":
        assert "invalid latest collector line" in output
    if status == "live":
        assert "start the interface with --ui and enable live following" in output
    if status == "stale":
        assert "return to DST and unpause live collection" in output


def test_check_live_with_explicit_unicode_path_does_not_create_files(
    tmp_path, monkeypatch, capsys
) -> None:
    log_path = tmp_path / "游戏 日志" / "client log.txt"
    monkeypatch.setattr(
        sys,
        "argv",
        ["route_planner.py", "--check-live", "--live-log", str(log_path)],
    )

    assert main() == 1
    output = capsys.readouterr().out
    assert str(log_path) in output
    assert "not found" in output
    assert not log_path.exists()
    assert not log_path.parent.exists()


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--ui", "--check-live"], "cannot be used together"),
        (["--check-live", "--sample-graph"], "cannot be combined"),
    ],
)
def test_check_live_rejects_incompatible_modes(monkeypatch, arguments, message: str) -> None:
    monkeypatch.setattr(sys, "argv", ["route_planner.py", *arguments])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 2


@pytest.mark.parametrize(
    ("port", "message"),
    [
        ("abc", "port must be an integer"),
        ("-1", "port must be between 0 and 65535"),
        ("65536", "port must be between 0 and 65535"),
    ],
)
def test_invalid_ui_port_is_reported_by_argument_parser(monkeypatch, capsys, port: str, message: str) -> None:
    monkeypatch.setattr(sys, "argv", ["route_planner.py", "--ui", "--port", port])

    with pytest.raises(SystemExit) as exit_info:
        main()

    captured = capsys.readouterr()
    assert exit_info.value.code == 2
    assert captured.out == ""
    assert message in captured.err
    assert "Traceback" not in captured.err


def test_invalid_observation_input_returns_clean_error(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, encoding=None: json.dumps({"directions": {"UP": {}}}),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["route_planner.py", "--observe-json", "directions.json"],
    )

    assert main() == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Unable to read observations: unknown direction 'UP'" in captured.err
    assert "Traceback" not in captured.err


def test_ui_startup_oserror_returns_clean_error(monkeypatch, capsys) -> None:
    def fail_to_start(*, port: int, open_browser: bool, live_log: Path | None) -> None:
        raise OSError("address already in use")

    monkeypatch.setattr(app, "run_app", fail_to_start)
    monkeypatch.setattr(sys, "argv", ["route_planner.py", "--ui", "--port", "8042"])

    assert main() == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Unable to start the local interface: address already in use\n"
