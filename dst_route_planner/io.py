from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dst_route_planner.models import Direction, DirectionObservation, Observation


class InputValidationError(ValueError):
    """Raised when a JSON observation does not match the manual input schema."""


_COMPASS_DIRECTIONS = tuple(direction for direction in Direction if direction is not Direction.UNKNOWN)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InputValidationError(f"{label} must be a JSON object.")
    return value


def _validate_schema_version(data: Mapping[str, Any], label: str, *, required: bool = False) -> int | None:
    if "schema_version" not in data:
        if required:
            raise InputValidationError(f"{label} must include schema_version: 1.")
        return None

    version = data["schema_version"]
    if type(version) is not int or version != 1:
        raise InputValidationError(f"{label} has unsupported schema_version; only version 1 is supported.")
    return version


def _string_list(data: Mapping[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise InputValidationError(f"{key} must be an array of strings.")
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise InputValidationError(f"{key}[{index}] must be a non-empty string.")
        strings.append(item)
    return strings


def _prefab_counts_from_data(data: Mapping[str, Any]) -> dict[str, int]:
    prefabs_seen = _string_list(data, "prefabs_seen")
    if "prefab_counts" not in data:
        return dict(Counter(prefabs_seen))

    raw_counts = data["prefab_counts"]
    if not isinstance(raw_counts, Mapping):
        raise InputValidationError("prefab_counts must be an object mapping prefab IDs to non-negative integers.")

    counts: dict[str, int] = {}
    for prefab, count in raw_counts.items():
        if not isinstance(prefab, str) or not prefab.strip():
            raise InputValidationError("prefab_counts keys must be non-empty prefab IDs.")
        if type(count) is not int or count < 0:
            raise InputValidationError(f"prefab_counts[{prefab!r}] must be a non-negative integer.")
        if count > 0:
            counts[prefab] = count

    # Listing a prefab in prefabs_seen is itself evidence that at least one was
    # seen. A zero count in the optional count map is accepted and omitted.
    for prefab in prefabs_seen:
        counts.setdefault(prefab, 1)
    return counts


def observation_from_dict(data: Mapping[str, Any]) -> Observation:
    """Parse one observation, accepting legacy input or manual schema version 1."""
    data = _mapping(data, "observation")
    _validate_schema_version(data, "observation")

    tile_types = _string_list(data, "tile_types")
    room_hints = _string_list(data, "room_hints")
    task_hints = _string_list(data, "task_hints")
    prefab_counts = _prefab_counts_from_data(data)

    connection_like = data.get("connection_like")
    if connection_like is not None and type(connection_like) is not bool:
        raise InputValidationError("connection_like must be true, false, or null.")
    background_like = data.get("background_like")
    if background_like is not None and type(background_like) is not bool:
        raise InputValidationError("background_like must be true, false, or null.")
    note = data.get("note", "")
    if not isinstance(note, str):
        raise InputValidationError("note must be a string.")

    return Observation(
        tile_types=frozenset(tile_types),
        prefabs_seen=frozenset(prefab_counts),
        prefab_counts=prefab_counts,
        room_hints=frozenset(room_hints),
        task_hints=frozenset(task_hints),
        connection_like=connection_like,
        background_like=background_like,
        note=note,
    )


def _direction_data(data: Mapping[str, Any]) -> Mapping[str, Any]:
    _validate_schema_version(data, "direction input")
    directions = data.get("directions")
    directions = _mapping(directions, "directions")

    # Accept either a version on the enclosing document or on the directions
    # object itself. This keeps the schema tag beside the values it describes.
    nested_version = _validate_schema_version(directions, "directions")
    outer_version = data.get("schema_version")
    if outer_version is not None and nested_version is not None and outer_version != nested_version:
        raise InputValidationError("direction input and directions schema_version values must match.")
    if nested_version is None:
        return directions
    return {key: value for key, value in directions.items() if key != "schema_version"}


def direction_observations_from_dict(data: Mapping[str, Any]) -> list[DirectionObservation]:
    data = _mapping(data, "direction input")
    raw_directions = _direction_data(data)
    allowed = {direction.value for direction in _COMPASS_DIRECTIONS}
    observations: list[DirectionObservation] = []
    for name, obs_data in raw_directions.items():
        if not isinstance(name, str) or name not in allowed:
            choices = ", ".join(direction.value for direction in _COMPASS_DIRECTIONS)
            raise InputValidationError(f"unknown direction {name!r}; use one of: {choices}.")
        observations.append(
            DirectionObservation(Direction(name), observation_from_dict(_mapping(obs_data, f"directions.{name}")))
        )
    return observations


def load_direction_observations(path: Path) -> list[DirectionObservation]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputValidationError(f"invalid JSON: {exc.msg}") from exc
    return direction_observations_from_dict(_mapping(data, "direction input"))
