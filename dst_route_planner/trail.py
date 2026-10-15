from __future__ import annotations

import json
from typing import Any


class TrailDataError(ValueError):
    """Raised when a validated replay cannot be projected as a trail."""


def project_trail(replay: bytes) -> dict[str, Any]:
    """Project a validated JSONL replay into its ordered player positions."""
    lines = replay.splitlines()
    if not lines:
        raise TrailDataError("journal is empty.")
    try:
        header = json.loads(lines[0].decode("utf-8"))
        frames = [json.loads(line.decode("utf-8")) for line in lines[1:]]
        points = [
            {
                "sequence": frame["snapshot"]["sequence"],
                "captured_at": frame["snapshot"]["captured_at"],
                "x": frame["snapshot"]["position"]["x"],
                "z": frame["snapshot"]["position"]["z"],
            }
            for frame in frames
        ]
        result = {
            "trail_version": 1,
            "id": header["id"],
            "world_id": header["world_id"],
            "world_kind": header["world_kind"],
            "session_id": header["session_id"],
            "frame_count": len(points),
            "points": points,
            "bounds": None,
        }
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise TrailDataError("journal could not be projected as a trail.") from exc

    if points:
        xs = [point["x"] for point in points]
        zs = [point["z"] for point in points]
        result["bounds"] = {
            "min_x": min(xs),
            "max_x": max(xs),
            "min_z": min(zs),
            "max_z": max(zs),
        }
    return result
