from __future__ import annotations

import json
from typing import Any


MAX_TRAIL_LANDMARKS = 500
MAX_TRAIL_TERRAIN_TILES = 2500


class TrailDataError(ValueError):
    """Raised when a validated replay cannot be projected as a trail."""


def project_trail(replay: bytes) -> dict[str, Any]:
    """Project a validated JSONL replay into player positions, terrain, and sightings."""
    lines = replay.splitlines()
    if not lines:
        raise TrailDataError("journal is empty.")
    try:
        header = json.loads(lines[0].decode("utf-8"))
        frames = [json.loads(line.decode("utf-8")) for line in lines[1:]]
        landmarks_by_key: dict[tuple[str, int | float, int | float], dict[str, Any]] = {}
        landmarks_truncated = False
        terrain_by_key: dict[tuple[int | float, int | float], dict[str, Any]] = {}
        terrain_truncated = False
        for frame in frames:
            snapshot = frame["snapshot"]
            sequence = snapshot["sequence"]
            captured_at = snapshot["captured_at"]
            seen_in_frame: set[tuple[str, int | float, int | float]] = set()
            for landmark in snapshot.get("landmarks", []):
                prefab = landmark["prefab"]
                x = landmark["x"]
                z = landmark["z"]
                key = (prefab, x, z)
                if key in seen_in_frame:
                    continue
                seen_in_frame.add(key)
                existing = landmarks_by_key.get(key)
                if existing is not None:
                    existing["last_seen"] = captured_at
                    existing["last_sequence"] = sequence
                    continue
                landmarks_by_key[key] = {
                    "prefab": prefab,
                    "x": x,
                    "z": z,
                    "first_seen": captured_at,
                    "last_seen": captured_at,
                    "first_sequence": sequence,
                    "last_sequence": sequence,
                }
            # Trim after the whole frame so overflow retention is independent
            # of the collector's landmark iteration order and matches the
            # public newest-first ranking.
            if len(landmarks_by_key) > MAX_TRAIL_LANDMARKS:
                ranked = sorted(
                    landmarks_by_key.values(),
                    key=lambda item: (
                        -item["last_sequence"],
                        item["prefab"],
                        item["x"],
                        item["z"],
                    ),
                )
                retained = ranked[:MAX_TRAIL_LANDMARKS]
                landmarks_by_key = {
                    (item["prefab"], item["x"], item["z"]): item for item in retained
                }
                landmarks_truncated = True

            terrain = snapshot.get("terrain")
            if terrain is not None:
                for tile in terrain["tiles"]:
                    x = tile["x"]
                    z = tile["z"]
                    key = (x, z)
                    existing = terrain_by_key.get(key)
                    if existing is not None and sequence < existing["last_sequence"]:
                        continue
                    projected_tile = {
                        "x": x,
                        "z": z,
                        "tile": tile["tile"],
                        "last_seen": captured_at,
                        "last_sequence": sequence,
                    }
                    if "passable" in tile:
                        projected_tile["passable"] = tile["passable"]
                    if "connections" in tile:
                        projected_tile["connections"] = dict(tile["connections"])
                    # Replace the entire cell snapshot: omitted passable or
                    # connections on a newer observation clears older values.
                    terrain_by_key[key] = projected_tile
                # Ranking follows capture order, not wall-clock timestamps.
                # Trim after each frame so memory stays bounded and the result
                # matches repeated application of the public retention rule.
                if len(terrain_by_key) > MAX_TRAIL_TERRAIN_TILES:
                    ranked_tiles = sorted(
                        terrain_by_key.values(),
                        key=lambda item: (
                            -item["last_sequence"], item["x"], item["z"]
                        ),
                    )
                    retained_tiles = ranked_tiles[:MAX_TRAIL_TERRAIN_TILES]
                    terrain_by_key = {
                        (item["x"], item["z"]): item for item in retained_tiles
                    }
                    terrain_truncated = True

        points = []
        for frame in frames:
            snapshot = frame["snapshot"]
            point = {
                "sequence": snapshot["sequence"],
                "captured_at": snapshot["captured_at"],
                "x": snapshot["position"]["x"],
                "z": snapshot["position"]["z"],
            }
            if "player_anchor" in snapshot:
                point["player_anchor"] = dict(snapshot["player_anchor"])
            points.append(point)
        result = {
            "trail_version": 1,
            "id": header["id"],
            "world_id": header["world_id"],
            "world_kind": header["world_kind"],
            "session_id": header["session_id"],
            "frame_count": len(points),
            "points": points,
            "bounds": None,
            "landmarks": sorted(
                landmarks_by_key.values(),
                key=lambda item: (
                    -item["last_sequence"],
                    item["prefab"],
                    item["x"],
                    item["z"],
                ),
            ),
            "landmarks_truncated": landmarks_truncated,
            "terrain": {
                "tile_size": 4,
                "tiles": sorted(
                    terrain_by_key.values(),
                    key=lambda item: (
                        -item["last_sequence"], item["x"], item["z"]
                    ),
                ),
                "truncated": terrain_truncated,
            },
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
