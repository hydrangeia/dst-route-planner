from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dst_route_planner.io import (
    InputValidationError,
    direction_observations_from_dict,
    observation_from_dict,
)


LIVE_MARKER = "DST_ROUTE_PLANNER_LIVE_V1 "
DEFAULT_TAIL_BYTES = 1024 * 1024
MAX_IDENTIFIER_LENGTH = 128
MAX_LANDMARKS = 4096
FRESHNESS_SECONDS = 5.0
MAX_CLOCK_SKEW_SECONDS = 2.0


class LiveSnapshotError(ValueError):
    """Raised when a marked collector line is not a valid live snapshot."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LiveSnapshotError(f"{label} must be a JSON object.")
    return value


def _finite_number(value: Any, label: str) -> float:
    if type(value) not in (int, float):
        raise LiveSnapshotError(f"{label} must be a finite number.")
    try:
        result = float(value)
    except OverflowError as exc:
        raise LiveSnapshotError(f"{label} must be a finite number.") from exc
    if not math.isfinite(result):
        raise LiveSnapshotError(f"{label} must be a finite number.")
    return result


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveSnapshotError(f"{label} must be a non-empty string.")
    if len(value) > MAX_IDENTIFIER_LENGTH:
        raise LiveSnapshotError(f"{label} must be at most {MAX_IDENTIFIER_LENGTH} characters.")
    return value


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LiveSnapshotError(f"snapshot contains duplicate JSON key {key!r}.")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise LiveSnapshotError(f"snapshot contains invalid JSON value {value}.")


def validate_snapshot(value: Any) -> dict[str, Any]:
    """Validate a collector snapshot and return its original JSON-shaped fields."""
    data = _mapping(value, "snapshot")
    required_fields = {
        "live_version",
        "world_id",
        "world_kind",
        "session_id",
        "sequence",
        "captured_at",
        "position",
        "camera_heading",
        "current",
        "directions",
    }
    allowed_fields = required_fields | {"landmarks"}
    missing_fields = required_fields - set(data)
    if missing_fields:
        names = ", ".join(sorted(missing_fields))
        raise LiveSnapshotError(f"snapshot is missing required field(s): {names}.")
    extra_fields = set(data) - allowed_fields
    if extra_fields:
        names = ", ".join(sorted(str(field) for field in extra_fields))
        raise LiveSnapshotError(f"snapshot has unsupported field(s): {names}.")
    if type(data["live_version"]) is not int or data["live_version"] != 1:
        raise LiveSnapshotError("snapshot must use live_version 1.")
    _identifier(data["world_id"], "world_id")
    _identifier(data["world_kind"], "world_kind")
    _identifier(data["session_id"], "session_id")

    sequence = data["sequence"]
    if type(sequence) is not int or sequence < 1:
        raise LiveSnapshotError("sequence must be an integer of at least 1.")
    _finite_number(data["captured_at"], "captured_at")
    _finite_number(data["camera_heading"], "camera_heading")

    position = _mapping(data["position"], "position")
    if set(position) != {"x", "y", "z"}:
        raise LiveSnapshotError("position must contain exactly x, y, and z.")
    for axis in ("x", "y", "z"):
        _finite_number(position[axis], f"position.{axis}")

    try:
        observation_from_dict(_mapping(data["current"], "current"))
        direction_observations_from_dict(
            {"schema_version": 1, "directions": _mapping(data["directions"], "directions")}
        )
    except InputValidationError as exc:
        raise LiveSnapshotError(str(exc)) from exc

    if "landmarks" in data:
        landmarks = data["landmarks"]
        if not isinstance(landmarks, list):
            raise LiveSnapshotError("landmarks must be an array.")
        if len(landmarks) > MAX_LANDMARKS:
            raise LiveSnapshotError(f"landmarks may contain at most {MAX_LANDMARKS} entries.")
        for index, item in enumerate(landmarks):
            landmark = _mapping(item, f"landmarks[{index}]")
            if set(landmark) != {"prefab", "x", "z"}:
                raise LiveSnapshotError(
                    f"landmarks[{index}] must contain exactly prefab, x, and z."
                )
            _identifier(landmark["prefab"], f"landmarks[{index}].prefab")
            _finite_number(landmark["x"], f"landmarks[{index}].x")
            _finite_number(landmark["z"], f"landmarks[{index}].z")

    return dict(data)


def read_latest_snapshot(
    path: Path | str,
    *,
    max_bytes: int = DEFAULT_TAIL_BYTES,
) -> dict[str, Any] | None:
    """Read the newest complete marked line from a bounded tail of a client log."""
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer.")
    try:
        with Path(path).open("rb") as log_file:
            log_file.seek(0, 2)
            size = log_file.tell()
            start = max(0, size - max_bytes)
            log_file.seek(start)
            tail = log_file.read(max_bytes)
    except FileNotFoundError:
        return None

    if start > 0:
        first_newline = tail.find(b"\n")
        if first_newline < 0:
            return None
        tail = tail[first_newline + 1 :]

    lines = tail.split(b"\n")
    if len(lines) < 2:
        return None
    marker = LIVE_MARKER.encode("ascii")
    for line in reversed(lines[:-1]):
        marker_at = line.find(marker)
        if marker_at < 0:
            continue
        json_bytes = line[marker_at + len(marker) :].rstrip(b"\r")
        try:
            text = json_bytes.decode("utf-8")
            value = json.loads(
                text,
                object_pairs_hook=_object_no_duplicates,
                parse_constant=_reject_json_constant,
            )
            return validate_snapshot(value)
        except LiveSnapshotError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise LiveSnapshotError(f"latest marked snapshot is invalid: {exc}") from exc
    return None


def age_seconds(snapshot: Mapping[str, Any], *, now: float) -> float:
    captured_at = _finite_number(snapshot.get("captured_at"), "captured_at")
    current_time = _finite_number(now, "current time")
    if captured_at > current_time + MAX_CLOCK_SKEW_SECONDS:
        raise LiveSnapshotError("captured_at is ahead of the local clock.")
    return max(0.0, current_time - captured_at)


def freshness_status(snapshot: Mapping[str, Any], *, now: float) -> tuple[str, float]:
    age = age_seconds(snapshot, now=now)
    if snapshot.get("world_kind") != "forest":
        return "unsupported_world", age
    if age > FRESHNESS_SECONDS:
        return "stale", age
    return "live", age


def nearest_visible_target(
    snapshot: Mapping[str, Any], target: str
) -> dict[str, Any] | None:
    position = snapshot["position"]
    candidates = [
        landmark
        for landmark in snapshot.get("landmarks", [])
        if landmark["prefab"] == target
    ]
    if not candidates:
        return None
    nearest = min(
        candidates,
        key=lambda landmark: math.hypot(
            float(landmark["x"]) - float(position["x"]),
            float(landmark["z"]) - float(position["z"]),
        ),
    )
    distance = math.hypot(
        float(nearest["x"]) - float(position["x"]),
        float(nearest["z"]) - float(position["z"]),
    )
    if not math.isfinite(distance):
        raise LiveSnapshotError("visible target distance is not finite.")
    return {
        "prefab": target,
        "x": nearest["x"],
        "z": nearest["z"],
        "distance": distance,
    }
