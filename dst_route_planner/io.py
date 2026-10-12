from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from dst_route_planner.models import Direction, DirectionObservation, Observation


def _prefab_counts_from_data(data: dict[str, Any]) -> dict[str, int]:
    prefabs_seen = [str(prefab) for prefab in data.get("prefabs_seen", [])]
    raw_counts = data.get("prefab_counts")
    if isinstance(raw_counts, dict):
        counts = {
            str(prefab): int(count)
            for prefab, count in raw_counts.items()
            if int(count) > 0
        }
        for prefab in prefabs_seen:
            counts.setdefault(prefab, 1)
        return counts
    return dict(Counter(prefabs_seen))


def observation_from_dict(data: dict[str, Any]) -> Observation:
    prefab_counts = _prefab_counts_from_data(data)
    return Observation(
        tile_types=frozenset(data.get("tile_types", [])),
        prefabs_seen=frozenset(prefab_counts),
        prefab_counts=prefab_counts,
        room_hints=frozenset(data.get("room_hints", [])),
        task_hints=frozenset(data.get("task_hints", [])),
        connection_like=data.get("connection_like"),
        background_like=data.get("background_like"),
        note=data.get("note", ""),
    )


def direction_observations_from_dict(data: dict[str, Any]) -> list[DirectionObservation]:
    raw_dirs = data.get("directions", {})
    observations: list[DirectionObservation] = []
    for direction, obs_data in raw_dirs.items():
        observations.append(DirectionObservation(Direction(direction), observation_from_dict(obs_data)))
    return observations


def load_direction_observations(path: Path) -> list[DirectionObservation]:
    return direction_observations_from_dict(json.loads(path.read_text(encoding="utf-8")))
