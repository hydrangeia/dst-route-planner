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
MAX_TERRAIN_TILES = 256
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
    allowed_fields = required_fields | {"landmarks", "terrain", "player_anchor"}
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
    position_x = _finite_number(position["x"], "position.x")
    _finite_number(position["y"], "position.y")
    position_z = _finite_number(position["z"], "position.z")

    player_anchor = None
    if "player_anchor" in data:
        player_anchor = _mapping(data["player_anchor"], "player_anchor")
        if set(player_anchor) != {"x", "z", "clear"}:
            raise LiveSnapshotError(
                "player_anchor must contain exactly x, z, and clear."
            )
        _finite_number(player_anchor["x"], "player_anchor.x")
        _finite_number(player_anchor["z"], "player_anchor.z")
        if type(player_anchor["clear"]) is not bool:
            raise LiveSnapshotError("player_anchor.clear must be a boolean.")

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

    if "terrain" in data:
        terrain = _mapping(data["terrain"], "terrain")
        if set(terrain) != {"tile_size", "tiles"}:
            raise LiveSnapshotError("terrain must contain exactly tile_size and tiles.")
        tile_size = _finite_number(terrain["tile_size"], "terrain.tile_size")
        if tile_size != 4:
            raise LiveSnapshotError("terrain.tile_size must equal 4.")
        tiles = terrain["tiles"]
        if not isinstance(tiles, list):
            raise LiveSnapshotError("terrain.tiles must be an array.")
        if len(tiles) > MAX_TERRAIN_TILES:
            raise LiveSnapshotError(
                f"terrain.tiles may contain at most {MAX_TERRAIN_TILES} entries."
            )
        coordinates: set[tuple[int | float, int | float]] = set()
        for index, item in enumerate(tiles):
            tile = _mapping(item, f"terrain.tiles[{index}]")
            required_tile_fields = {"x", "z", "tile"}
            allowed_tile_fields = required_tile_fields | {"passable", "connections"}
            if not required_tile_fields <= set(tile) or set(tile) - allowed_tile_fields:
                raise LiveSnapshotError(
                    f"terrain.tiles[{index}] must contain x, z, and tile, with only optional passable or connections."
                )
            _finite_number(tile["x"], f"terrain.tiles[{index}].x")
            _finite_number(tile["z"], f"terrain.tiles[{index}].z")
            _identifier(tile["tile"], f"terrain.tiles[{index}].tile")
            if "passable" in tile and type(tile["passable"]) is not bool:
                raise LiveSnapshotError(
                    f"terrain.tiles[{index}].passable must be a boolean."
                )
            if "connections" in tile:
                connections = tile["connections"]
                if not isinstance(connections, Mapping):
                    raise LiveSnapshotError(
                        f"terrain.tiles[{index}].connections must be an object."
                    )
                if any(
                    type(direction) is not str or direction not in {"east", "north"}
                    for direction in connections
                ):
                    raise LiveSnapshotError(
                        f"terrain.tiles[{index}].connections may contain only east and north."
                    )
                for direction, connected in connections.items():
                    if type(connected) is not bool:
                        raise LiveSnapshotError(
                            f"terrain.tiles[{index}].connections.{direction} must be a boolean."
                        )
            coordinate = (tile["x"], tile["z"])
            if coordinate in coordinates:
                raise LiveSnapshotError(
                    f"terrain.tiles contains duplicate coordinate ({tile['x']!r}, {tile['z']!r})."
                )
            coordinates.add(coordinate)

        # Resolve references only after every tile has passed its shape,
        # value, and duplicate-coordinate checks.
        tile_by_coordinate = {(tile["x"], tile["z"]): tile for tile in tiles}
        for index, tile in enumerate(tiles):
            connections = tile.get("connections")
            if not connections:
                continue
            if tile.get("passable") is not True:
                raise LiveSnapshotError(
                    f"terrain.tiles[{index}].connections requires passable=true on this tile."
                )
            x = tile["x"]
            z = tile["z"]
            for direction in connections:
                neighbor_coordinate = (
                    (x + 4, z) if direction == "east" else (x, z + 4)
                )
                neighbor = tile_by_coordinate.get(neighbor_coordinate)
                if neighbor is None or neighbor is tile or neighbor.get("passable") is not True:
                    raise LiveSnapshotError(
                        f"terrain.tiles[{index}].connections.{direction} requires a distinct neighboring tile with passable=true."
                    )

    if player_anchor is not None:
        if "terrain" not in data:
            raise LiveSnapshotError("player_anchor requires observed terrain tiles.")
        anchor_coordinate = (player_anchor["x"], player_anchor["z"])
        anchor_tile = tile_by_coordinate.get(anchor_coordinate)
        if anchor_tile is None or anchor_tile.get("passable") is not True:
            raise LiveSnapshotError(
                "player_anchor must reference a passable terrain tile center."
            )

        matching_tiles: list[Mapping[str, Any]] = []
        imprecise_match = False
        for tile in data["terrain"]["tiles"]:
            center_x = _finite_number(tile["x"], "terrain tile x")
            center_z = _finite_number(tile["z"], "terrain tile z")
            min_x = center_x - 2.0
            max_x = center_x + 2.0
            min_z = center_z - 2.0
            max_z = center_z + 2.0
            bounds_valid = (
                math.isfinite(min_x)
                and math.isfinite(max_x)
                and math.isfinite(min_z)
                and math.isfinite(max_z)
                and min_x < center_x < max_x
                and min_z < center_z < max_z
                and max_x - min_x == 4.0
                and max_z - min_z == 4.0
            )
            if not bounds_valid:
                if (
                    abs(position_x - center_x) <= 2.0
                    and abs(position_z - center_z) <= 2.0
                ):
                    imprecise_match = True
                continue
            if (
                min_x <= position_x < max_x
                and min_z <= position_z < max_z
            ):
                matching_tiles.append(tile)

        if (
            imprecise_match
            or len(matching_tiles) != 1
            or matching_tiles[0] is not anchor_tile
        ):
            raise LiveSnapshotError(
                "player_anchor must reference the unique passable tile containing position."
            )

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
