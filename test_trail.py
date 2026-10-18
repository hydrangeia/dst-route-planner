from __future__ import annotations

import json

from dst_route_planner.exploration import exploration_id
from dst_route_planner.trail import project_trail


def _journal(
    points: list[tuple[int, int | float, int | float, int | float]],
    *,
    world_id: str = "world-trail",
    world_kind: str = "forest",
    session_id: str = "session-trail",
    landmarks_by_frame: list[list[dict]] | None = None,
    terrain_by_frame: list[list[dict]] | None = None,
    player_anchors_by_frame: list[dict | None] | None = None,
) -> bytes:
    journal_id = exploration_id(world_id, world_kind, session_id)
    header = {
        "replay_version": 1,
        "id": journal_id,
        "world_id": world_id,
        "world_kind": world_kind,
        "session_id": session_id,
    }
    lines = [json.dumps(header, separators=(",", ":"))]
    for frame_index, (sequence, captured_at, x, z) in enumerate(points):
        frame = {
            "replay_version": 1,
            "received_at": "2026-10-15T00:00:00.000000Z",
            "target": "panflute",
            "seed": 0,
            "plan": {"private_plan_detail": "do not expose"},
            "snapshot": {
                "sequence": sequence,
                "captured_at": captured_at,
                "position": {"x": x, "y": 0, "z": z},
                "current": {"tile_types": ["GRASS"]},
                "directions": {"north": {"note": "do not expose"}},
            },
        }
        if landmarks_by_frame is not None and frame_index < len(landmarks_by_frame):
            frame["snapshot"]["landmarks"] = landmarks_by_frame[frame_index]
        if terrain_by_frame is not None and frame_index < len(terrain_by_frame):
            frame["snapshot"]["terrain"] = {
                "tile_size": 4,
                "tiles": terrain_by_frame[frame_index],
            }
        if (
            player_anchors_by_frame is not None
            and frame_index < len(player_anchors_by_frame)
            and player_anchors_by_frame[frame_index] is not None
        ):
            frame["snapshot"]["player_anchor"] = player_anchors_by_frame[frame_index]
        lines.append(json.dumps(frame, separators=(",", ":")))
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_project_trail_preserves_every_stationary_and_asymmetric_point() -> None:
    content = _journal(
        [
            (1, 1800000000.125, -12, 3.5),
            (2, 1800000001.25, -12, 3.5),
            (3, 1800000002.5, 8.25, -20),
        ]
    )

    trail = project_trail(content)

    assert trail == {
        "trail_version": 1,
        "id": exploration_id("world-trail", "forest", "session-trail"),
        "world_id": "world-trail",
        "world_kind": "forest",
        "session_id": "session-trail",
        "frame_count": 3,
        "points": [
            {"sequence": 1, "captured_at": 1800000000.125, "x": -12, "z": 3.5},
            {"sequence": 2, "captured_at": 1800000001.25, "x": -12, "z": 3.5},
            {"sequence": 3, "captured_at": 1800000002.5, "x": 8.25, "z": -20},
        ],
        "bounds": {"min_x": -12, "max_x": 8.25, "min_z": -20, "max_z": 3.5},
        "landmarks": [],
        "landmarks_truncated": False,
        "terrain": {"tile_size": 4, "tiles": [], "truncated": False},
    }
    assert "private_plan_detail" not in json.dumps(trail)
    assert "directions" not in trail


def test_project_trail_copies_only_each_frames_player_anchor() -> None:
    trail = project_trail(
        _journal(
            [(1, 30, -2, 3), (2, 20, 0, 0), (3, 10, 4, -1)],
            player_anchors_by_frame=[
                {"x": -4, "z": 4, "clear": False},
                None,
                {"x": 4, "z": 0, "clear": True},
            ],
        )
    )

    assert trail["points"] == [
        {
            "sequence": 1,
            "captured_at": 30,
            "x": -2,
            "z": 3,
            "player_anchor": {"x": -4, "z": 4, "clear": False},
        },
        {"sequence": 2, "captured_at": 20, "x": 0, "z": 0},
        {
            "sequence": 3,
            "captured_at": 10,
            "x": 4,
            "z": -1,
            "player_anchor": {"x": 4, "z": 0, "clear": True},
        },
    ]
    assert "player_anchor" not in trail


def test_project_trail_keeps_sessions_separate_and_empty_bounds_null() -> None:
    first = project_trail(_journal([(1, 10, 1, 2)]))
    second = project_trail(
        _journal([(1, 11, 99, -45)], session_id="another-session")
    )
    empty = project_trail(_journal([]))

    assert first["id"] != second["id"]
    assert first["session_id"] == "session-trail"
    assert first["points"] == [{"sequence": 1, "captured_at": 10, "x": 1, "z": 2}]
    assert second["session_id"] == "another-session"
    assert second["points"] == [{"sequence": 1, "captured_at": 11, "x": 99, "z": -45}]
    assert empty["frame_count"] == 0
    assert empty["points"] == []
    assert empty["bounds"] is None
    assert empty["landmarks"] == []
    assert empty["landmarks_truncated"] is False
    assert empty["terrain"] == {"tile_size": 4, "tiles": [], "truncated": False}


def test_project_trail_deduplicates_exact_sightings_and_keeps_first_last_values() -> None:
    trail = project_trail(
        _journal(
            [
                (1, 200, 0, 0),
                (2, 100, 1, 0),
                (3, 300, 2, 0),
            ],
            landmarks_by_frame=[
                [
                    {"prefab": "pigking", "x": 4, "z": 5},
                    {"prefab": "pigking", "x": 4, "z": 5},
                    {"prefab": "pigking", "x": 4.25, "z": 5},
                    {"prefab": "pigking", "x": 4, "z": 7},
                    {"prefab": "panflute", "x": 4, "z": 5},
                    {"prefab": "pigking", "x": 2, "z": 9},
                ],
                [
                    {"prefab": "pigking", "x": 4, "z": 5},
                    {"prefab": "pigking", "x": 4, "z": 7},
                    {"prefab": "panflute", "x": 4, "z": 5},
                    {"prefab": "pigking", "x": 4, "z": 5},
                ],
                [
                    {"prefab": "pigking", "x": 4, "z": 5},
                    {"prefab": "pigking", "x": 4, "z": 7},
                    {"prefab": "panflute", "x": 4, "z": 5},
                    {"prefab": "pigking", "x": 2, "z": 9},
                ],
            ],
        )
    )

    assert trail["landmarks"] == [
        {
            "prefab": "panflute",
            "x": 4,
            "z": 5,
            "first_seen": 200,
            "last_seen": 300,
            "first_sequence": 1,
            "last_sequence": 3,
        },
        {
            "prefab": "pigking",
            "x": 2,
            "z": 9,
            "first_seen": 200,
            "last_seen": 300,
            "first_sequence": 1,
            "last_sequence": 3,
        },
        {
            "prefab": "pigking",
            "x": 4,
            "z": 5,
            "first_seen": 200,
            "last_seen": 300,
            "first_sequence": 1,
            "last_sequence": 3,
        },
        {
            "prefab": "pigking",
            "x": 4,
            "z": 7,
            "first_seen": 200,
            "last_seen": 300,
            "first_sequence": 1,
            "last_sequence": 3,
        },
        {
            "prefab": "pigking",
            "x": 4.25,
            "z": 5,
            "first_seen": 200,
            "last_seen": 200,
            "first_sequence": 1,
            "last_sequence": 1,
        },
    ]
    assert trail["landmarks_truncated"] is False


def test_project_trail_trims_frame_overflow_by_rank_and_keeps_newer_sightings() -> None:
    landmarks = [
        {"prefab": "monument", "x": coordinate, "z": -coordinate}
        for coordinate in reversed(range(501))
    ]
    first_frame_replay = _journal(
        [(1, 10, 0, 0)],
        landmarks_by_frame=[landmarks],
    )
    first_frame_trail = project_trail(first_frame_replay)
    first_frame_landmarks = first_frame_trail["landmarks"]
    assert len(first_frame_landmarks) == 500
    assert [item["x"] for item in first_frame_landmarks] == list(range(500))
    assert first_frame_trail["landmarks_truncated"] is True

    trail = project_trail(
        _journal(
            [(1, 10, 0, 0), (2, 20, 1, 0)],
            landmarks_by_frame=[
                landmarks,
                [
                    {"prefab": "monument", "x": 500, "z": -500},
                    {"prefab": "monument", "x": 499, "z": -499},
                ],
            ],
        )
    )

    retained = trail["landmarks"]
    assert len(retained) == 500
    assert trail["landmarks_truncated"] is True
    assert retained[0] == {
        "prefab": "monument",
        "x": 499,
        "z": -499,
        "first_seen": 10,
        "last_seen": 20,
        "first_sequence": 1,
        "last_sequence": 2,
    }
    assert retained[1]["x"] == 500
    assert retained[1]["last_sequence"] == 2
    assert retained[2]["x"] == 0
    assert retained[2]["last_sequence"] == 1
    assert retained[-1]["x"] == 497
    assert {item["x"] for item in retained} == {499, 500, *range(498)}


def test_project_trail_uses_sequence_for_latest_tile_and_time_when_clock_moves_back() -> None:
    trail = project_trail(
        _journal(
            [(1, 300, 0, 0), (2, 100, 1, 0), (3, 50, 2, 0)],
            terrain_by_frame=[
                [
                    {
                        "x": 1,
                        "z": 2,
                        "tile": "GRASS",
                        "passable": True,
                        "connections": {"east": True, "north": False},
                    },
                    {"x": -1, "z": 0, "tile": "MARSH", "passable": False},
                ],
                [
                    {
                        "x": 1,
                        "z": 2,
                        "tile": "FOREST",
                        "passable": False,
                        "connections": {"east": False},
                    },
                    {"x": 3, "z": 4, "tile": "ROCKY"},
                ],
                [
                    {"x": 1, "z": 2, "tile": "DECIDUOUS"},
                    {
                        "x": 5,
                        "z": 6,
                        "tile": "GRASS",
                        "passable": True,
                        "connections": {"north": False},
                    },
                ],
            ],
        )
    )

    assert trail["terrain"] == {
        "tile_size": 4,
        "tiles": [
            {"x": 1, "z": 2, "tile": "DECIDUOUS", "last_seen": 50, "last_sequence": 3},
            {
                "x": 5,
                "z": 6,
                "tile": "GRASS",
                "last_seen": 50,
                "last_sequence": 3,
                "passable": True,
                "connections": {"north": False},
            },
            {"x": 3, "z": 4, "tile": "ROCKY", "last_seen": 100, "last_sequence": 2},
            {
                "x": -1,
                "z": 0,
                "tile": "MARSH",
                "last_seen": 300,
                "last_sequence": 1,
                "passable": False,
            },
        ],
        "truncated": False,
    }
    assert "passable" not in trail["terrain"]["tiles"][0]
    assert "connections" not in trail["terrain"]["tiles"][0]
    assert trail["terrain"]["tiles"][1]["connections"] == {"north": False}
    assert trail["terrain"]["tiles"][3]["passable"] is False


def test_project_trail_caps_terrain_at_2500_by_latest_sequence_then_coordinates() -> None:
    terrain_by_frame = [
        [
            {"x": frame_index * 256 + tile_index, "z": 0, "tile": f"T{frame_index}-{tile_index}"}
            for tile_index in range(256)
        ]
        for frame_index in range(10)
    ]
    points = [(sequence, 2000 - sequence * 100, sequence, 0) for sequence in range(1, 11)]

    terrain = project_trail(_journal(points, terrain_by_frame=terrain_by_frame))["terrain"]

    assert terrain["truncated"] is True
    assert len(terrain["tiles"]) == 2500
    assert terrain["tiles"][0] == {
        "x": 2304, "z": 0, "tile": "T9-0", "last_seen": 1000, "last_sequence": 10
    }
    assert terrain["tiles"][255]["last_sequence"] == 10
    assert terrain["tiles"][256]["last_sequence"] == 9
    assert terrain["tiles"][2303]["last_sequence"] == 2
    assert terrain["tiles"][2304]["x"] == 0
    assert terrain["tiles"][2304]["last_sequence"] == 1
    assert terrain["tiles"][-1]["x"] == 195
