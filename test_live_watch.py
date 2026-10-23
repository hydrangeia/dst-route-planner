"""Tests for the continuous, read-only live diagnostic watcher."""

from __future__ import annotations

from pathlib import Path

from dst_route_planner.live_watch import watch_live_log


def run_responses(monkeypatch, responses: list[dict], *, capsys) -> tuple[int, str]:
    calls: list[Path | str] = []
    sleeps: list[float] = []

    def inspect(path):
        calls.append(path)
        return responses[len(calls) - 1]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == len(responses):
            raise KeyboardInterrupt

    monkeypatch.setattr("builtins.print", print)
    result = watch_live_log("client.log", inspect=inspect, sleep=sleep)
    output = capsys.readouterr().out
    assert calls == ["client.log"] * len(responses)
    assert sleeps == [1.0] * len(responses)
    return result, output


def live_result(
    *,
    sequence: int = 4,
    captured_at: float = 100.0,
    age: float = 0.2,
    heading: float = 0.5,
    status: str = "live",
) -> dict:
    return {
        "status": status,
        "sequence": sequence,
        "captured_at": captured_at,
        "age_seconds": age,
        "world_kind": "forest",
        "position": {"x": -4, "y": 1, "z": 12},
        "camera_heading": heading,
        "observation_summary": {
            "landmarks": 2,
            "terrain_available": True,
            "terrain_tiles": 5,
            "passable_tiles": 3,
            "blocked_tiles": 1,
            "unknown_tiles": 1,
            "clear_connections": 2,
            "blocked_connections": 1,
            "player_anchor": "clear",
        },
    }


def test_unchanged_waiting_or_fresh_state_does_not_spam(monkeypatch, capsys) -> None:
    result, output = run_responses(
        monkeypatch,
        [
            live_result(age=0.2),
            live_result(age=0.8),
            live_result(age=1.4),
        ],
        capsys=capsys,
    )

    assert result == 0
    assert output.count("Live watch: live") == 1
    assert "age=0.2s" in output
    assert "Client log: client.log" in output
    assert "every 1s. Press Ctrl+C to stop" in output
    assert "seq=4" in output
    assert "world=forest x=-4 z=12" in output
    assert "camera_heading=0.5" in output
    assert "landmarks=2 tiles=5 passable=3 blocked=1 unknown=1" in output
    assert "links=2 clear/1 blocked anchor=clear" in output
    assert output.endswith("Live watch: stopped.\n")


def test_unchanged_waiting_and_stale_states_do_not_spam(monkeypatch, capsys) -> None:
    result, output = run_responses(
        monkeypatch,
        [
            {"status": "waiting"},
            {"status": "waiting"},
            live_result(status="stale", age=8.0),
            live_result(status="stale", age=9.0),
        ],
        capsys=capsys,
    )

    assert result == 0
    assert output.count("Live watch: waiting") == 1
    assert output.count("Live watch: stale") == 1


def test_paused_stale_transition_and_recovery_print_each_change(monkeypatch, capsys) -> None:
    result, output = run_responses(
        monkeypatch,
        [
            live_result(status="live", age=4.9),
            live_result(status="stale", age=5.9),
            live_result(status="live", age=0.1),
        ],
        capsys=capsys,
    )

    assert result == 0
    assert output.count("Live watch: live") == 2
    assert output.count("Live watch: stale") == 1
    assert "age=5.9s" in output


def test_missing_log_recovers_to_live(monkeypatch, capsys) -> None:
    result, output = run_responses(
        monkeypatch,
        [{"status": "missing_log"}, live_result()],
        capsys=capsys,
    )

    assert result == 0
    assert "client log not found" in output
    assert "start DST once to create it" in output
    assert "Live watch: live" in output


def test_log_error_recovers_to_live(monkeypatch, capsys) -> None:
    result, output = run_responses(
        monkeypatch,
        [{"status": "error", "error": "sharing violation"}, live_result()],
        capsys=capsys,
    )

    assert result == 0
    assert "error: sharing violation" in output
    assert "check that the log is readable" in output
    assert "Live watch: live" in output


def test_same_sequence_updates_when_capture_time_or_camera_heading_changes(
    monkeypatch, capsys
) -> None:
    result, output = run_responses(
        monkeypatch,
        [
            live_result(sequence=9, captured_at=100.0, age=0.1, heading=0.5),
            live_result(sequence=9, captured_at=101.0, age=0.1, heading=0.5),
            live_result(sequence=9, captured_at=101.0, age=0.1, heading=1.5),
        ],
        capsys=capsys,
    )

    assert result == 0
    assert output.count("Live watch: live") == 3
    assert output.count("seq=9") == 3
    assert "camera_heading=0.5" in output
    assert "camera_heading=1.5" in output


def test_same_frame_fields_print_when_world_kind_changes(monkeypatch, capsys) -> None:
    changed_kind = live_result()
    changed_kind["world_kind"] = "cave"
    result, output = run_responses(
        monkeypatch,
        [live_result(), changed_kind],
        capsys=capsys,
    )

    assert result == 0
    assert output.count("Live watch: live") == 2
    assert "world=forest" in output
    assert "world=cave" in output


def test_very_large_sequence_prints_exactly(monkeypatch, capsys) -> None:
    sequence = 10**400
    result, output = run_responses(
        monkeypatch,
        [live_result(sequence=sequence)],
        capsys=capsys,
    )

    assert result == 0
    assert f"seq={sequence}" in output


def test_optional_fields_from_older_checks_remain_readable(monkeypatch, capsys) -> None:
    result, output = run_responses(
        monkeypatch,
        [
            {
                "status": "live",
                "sequence": 2,
                "age_seconds": 0.3,
                "position": {"x": 1, "z": 2},
            }
        ],
        capsys=capsys,
    )

    assert result == 0
    assert "seq=2 age=0.3s" in output
    assert "x=1 z=2" in output
    assert "camera_heading=unknown" in output
    assert "summary=unavailable" in output


def test_keyboard_interrupt_prints_stopped_and_returns_zero(capsys) -> None:
    output: list[str] = []

    def interrupt(_seconds: float) -> None:
        raise KeyboardInterrupt

    result = watch_live_log(
        Path("client.log"),
        inspect=lambda _path: {"status": "waiting"},
        sleep=interrupt,
        emit=output.append,
    )

    assert result == 0
    assert output[0] == "Client log: client.log"
    assert output[-1] == "Live watch: stopped."
    assert any("Live watch: waiting" in line for line in output)


def test_keyboard_interrupt_during_startup_emission_stops_cleanly() -> None:
    output: list[str] = []
    interrupt_next_emit = True

    def emit(line: str) -> None:
        nonlocal interrupt_next_emit
        if interrupt_next_emit:
            interrupt_next_emit = False
            raise KeyboardInterrupt
        output.append(line)

    result = watch_live_log(
        Path("client.log"),
        inspect=lambda _path: {"status": "waiting"},
        sleep=lambda _seconds: None,
        emit=emit,
    )

    assert result == 0
    assert output == ["Live watch: stopped."]
