"""CLI coverage for the local interface and user-facing input errors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from dst_route_planner import app
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
