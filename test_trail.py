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
    for sequence, captured_at, x, z in points:
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
                "landmarks": [{"prefab": "pigking", "x": 4, "z": 5}],
            },
        }
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
    }
    assert "private_plan_detail" not in json.dumps(trail)
    assert "directions" not in trail
    assert "landmarks" not in trail


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
