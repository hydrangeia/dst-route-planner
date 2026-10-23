"""Continuous, read-only diagnostics for the client collector log."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

from dst_route_planner.connection import inspect_live_log


_MISSING = object()
_SIGNATURE_FIELDS = (
    "status",
    "sequence",
    "captured_at",
    "world_kind",
    "position",
    "camera_heading",
    "observation_summary",
    "error",
)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze(item) for item in value)
    if value is None or type(value) in (str, int, float, bool):
        return value
    return repr(value)


def _signature(result: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        (field, _freeze(result[field]) if field in result else _MISSING)
        for field in _SIGNATURE_FIELDS
    )


def _display(value: Any, fallback: str = "unknown") -> str:
    if type(value) is int:
        return str(value)
    if type(value) is float:
        return f"{value:g}"
    if isinstance(value, str) and value:
        return value
    return fallback


def _summary_text(summary: Any) -> str:
    if not isinstance(summary, Mapping):
        return "summary=unavailable"

    if summary.get("terrain_available") is False:
        tiles = "not-provided"
    else:
        tiles = _display(summary.get("terrain_tiles"))
    return (
        f"landmarks={_display(summary.get('landmarks'))} "
        f"tiles={tiles} "
        f"passable={_display(summary.get('passable_tiles'))} "
        f"blocked={_display(summary.get('blocked_tiles'))} "
        f"unknown={_display(summary.get('unknown_tiles'))} "
        f"links={_display(summary.get('clear_connections'))} clear/"
        f"{_display(summary.get('blocked_connections'))} blocked "
        f"anchor={_display(summary.get('player_anchor'))}"
    )


def _diagnostic_line(result: Mapping[str, Any]) -> str:
    status = result.get("status", "error")
    if status in {"live", "stale"}:
        position = result.get("position")
        if isinstance(position, Mapping):
            x = _display(position.get("x"))
            z = _display(position.get("z"))
        else:
            x = z = "unknown"
        age = result.get("age_seconds")
        age_text = f"{_display(age)}s" if type(age) in (int, float) else "unknown"
        return (
            f"Live watch: {status} seq={_display(result.get('sequence'))} "
            f"age={age_text} world={_display(result.get('world_kind'))} "
            f"x={x} z={z} "
            f"camera_heading={_display(result.get('camera_heading'))}; "
            f"{_summary_text(result.get('observation_summary'))}"
        )

    if status == "waiting":
        return (
            "Live watch: waiting; next: enable the client collector mod and enter a world."
        )
    if status == "missing_log":
        return (
            "Live watch: client log not found; next: start DST once to create it, "
            "or set --live-log PATH."
        )
    if status == "disabled":
        return "Live watch: disabled; next: pass --live-log PATH or use --live-log auto."

    error = result.get("error")
    detail = str(error) if error else "unknown status"
    return (
        f"Live watch: error: {detail}; next: check that the log is readable "
        "and its latest collector line is valid."
    )


def watch_live_log(
    live_log: Path | str,
    *,
    inspect: Callable[[Path | str], Mapping[str, Any]] | None = None,
    sleep: Callable[[float], None] | None = None,
    emit: Callable[[str], None] | None = None,
) -> int:
    """Poll one resolved log each second, printing only new diagnostics."""
    inspect_log = inspect or inspect_live_log
    pause = sleep or time.sleep
    write_line = emit or (lambda line: print(line, flush=True))

    previous = _MISSING
    try:
        write_line(f"Client log: {live_log}")
        write_line("Watching live collector every 1s. Press Ctrl+C to stop.")
        while True:
            try:
                result = inspect_log(live_log)
            except OSError as error:
                result = {"status": "error", "error": str(error)}
            current = _signature(result)
            if current != previous:
                write_line(_diagnostic_line(result))
                previous = current
            pause(1.0)
    except KeyboardInterrupt:
        write_line("Live watch: stopped.")
        return 0
