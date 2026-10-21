from __future__ import annotations

import json
import math
import time
from pathlib import Path

import pytest

from dst_route_planner.live import (
    LIVE_MARKER,
    LiveSnapshotError,
    freshness_status,
    read_latest_snapshot,
    read_snapshot_batch,
    validate_snapshot,
)


def _snapshot(
    *,
    captured_at: float = 100.0,
    session_id: str = "session-a",
    sequence: int = 1,
    world_kind: str = "forest",
    terrain: dict | None = None,
    player_anchor: dict | None = None,
) -> dict:
    snapshot = {
        "live_version": 1,
        "world_id": "world-123",
        "world_kind": world_kind,
        "session_id": session_id,
        "sequence": sequence,
        "captured_at": captured_at,
        "position": {"x": 12.5, "y": 0, "z": -8},
        "camera_heading": 1.25,
        "current": {
            "schema_version": 1,
            "tile_types": ["FUTURE_TILE"],
            "prefab_counts": {"unknown_prefab": 2},
            "note": "near spawn",
        },
        "directions": {
            "north": {"tile_types": ["DECIDUOUS"], "prefabs_seen": ["panflute"]},
            "east": {"tile_types": ["GRASS"]},
        },
        "landmarks": [
            {"prefab": "panflute", "x": 13, "z": -8},
        ],
    }
    if terrain is not None:
        snapshot["terrain"] = terrain
    if player_anchor is not None:
        snapshot["player_anchor"] = player_anchor
    return snapshot


def _line(snapshot: dict, prefix: str = "") -> str:
    return f"{prefix}{LIVE_MARKER}{json.dumps(snapshot, separators=(',', ':'))}\n"


def _anchor_snapshot(
    anchor: object,
    *,
    position: tuple[int | float, int | float] = (0, 0),
    tiles: list[dict] | None = None,
) -> dict:
    if tiles is None:
        tiles = [{"x": 0, "z": 0, "tile": "GRASS", "passable": True}]
    snapshot = _snapshot(terrain={"tile_size": 4, "tiles": tiles})
    snapshot["position"].update(x=position[0], z=position[1])
    snapshot["player_anchor"] = anchor
    return snapshot


def test_reader_finds_newest_complete_marker_with_a_log_prefix(tmp_path) -> None:
    path = tmp_path / "client.log"
    older = _snapshot(session_id="old", sequence=40)
    newest = _snapshot(session_id="new", sequence=1)
    path.write_text(
        "ordinary client output\n"
        + _line(older, "[00:00:01] log: ")
        + "unrelated entry\n"
        + _line(newest, "[00:00:02] log: "),
        encoding="utf-8",
    )

    assert read_latest_snapshot(path) == newest


def test_batch_reader_keeps_valid_marked_lines_in_order_and_skips_invalid_lines(tmp_path) -> None:
    path = tmp_path / "client.log"
    first = _snapshot(session_id="first", sequence=1)
    second = _snapshot(session_id="second", sequence=2)
    lines = [
        b"ordinary client output\n",
        _line(first, "[00:00:01] log: ").encode("utf-8").replace(b"\n", b"\r\n"),
        (LIVE_MARKER + "{malformed json}\n").encode("utf-8"),
        LIVE_MARKER.encode("ascii") + b"\xff\n",
        LIVE_MARKER.encode("ascii") + b'{"live_version":1,"live_version":1}\n',
        (LIVE_MARKER + '{"live_version":1,"captured_at":NaN}\n').encode("utf-8"),
        _line(second, "[00:00:02] log: ").encode("utf-8").replace(b"\n", b"\r\n"),
    ]
    path.write_bytes(b"".join(lines))

    assert read_snapshot_batch(path) == [first, second]


def test_batch_reader_waits_for_an_incomplete_tail_to_finish(tmp_path) -> None:
    path = tmp_path / "client.log"
    first = _snapshot(sequence=1)
    second = _snapshot(sequence=2)
    second_line = _line(second).encode("utf-8")
    path.write_bytes(_line(first).encode("utf-8") + second_line[:-2])

    assert read_snapshot_batch(path) == [first]

    with path.open("ab") as output:
        output.write(b"}\n")
    assert read_snapshot_batch(path) == [first, second]


def test_batch_reader_discards_a_starting_partial_line_from_the_bounded_tail(tmp_path) -> None:
    path = tmp_path / "client.log"
    partial = _snapshot(session_id="partial", sequence=1)
    newest = _snapshot(session_id="newest", sequence=1)
    partial_line = (b"x" * 128) + _line(partial).encode("utf-8")
    newest_line = _line(newest).encode("utf-8")
    contents = partial_line + newest_line
    max_bytes = len(contents) - 32
    path.write_bytes(contents)

    assert read_snapshot_batch(path, max_bytes=max_bytes) == [newest]


def test_batch_reader_handles_missing_and_rewritten_logs(tmp_path) -> None:
    path = tmp_path / "client.log"
    assert read_snapshot_batch(path) == []

    first = _snapshot(session_id="old-session", sequence=20)
    path.write_bytes((_line(first) + _line(first, "second: ")).encode("utf-8"))
    assert read_snapshot_batch(path) == [first, first]

    rewritten = _snapshot(session_id="new-session", sequence=1)
    path.write_bytes(_line(rewritten).encode("utf-8"))
    assert read_snapshot_batch(path) == [rewritten]


@pytest.mark.parametrize("max_bytes", [0, -1, True, 1024.0])
def test_batch_reader_rejects_invalid_tail_sizes(tmp_path, max_bytes) -> None:
    with pytest.raises(ValueError, match="max_bytes must be a positive integer"):
        read_snapshot_batch(tmp_path / "client.log", max_bytes=max_bytes)


def test_batch_reader_keeps_non_missing_os_errors_visible(tmp_path, monkeypatch) -> None:
    def fail_open(self, *args, **kwargs):
        raise PermissionError("log is not readable")

    monkeypatch.setattr(Path, "open", fail_open)
    with pytest.raises(PermissionError, match="not readable"):
        read_snapshot_batch(tmp_path / "client.log")


def test_reader_ignores_partial_tail_but_rejects_latest_malformed_complete_line(tmp_path) -> None:
    path = tmp_path / "client.log"
    valid = _snapshot(sequence=7)
    path.write_text(_line(valid), encoding="utf-8")
    with path.open("a", encoding="utf-8") as output:
        output.write(LIVE_MARKER + '{"live_version":1')

    assert read_latest_snapshot(path) == valid

    with path.open("a", encoding="utf-8") as output:
        output.write("}\n")
    assert read_snapshot_batch(path) == [valid]
    with pytest.raises(LiveSnapshotError, match="missing required field"):
        read_latest_snapshot(path)


def test_reader_handles_missing_files_truncation_rotation_and_session_change(tmp_path) -> None:
    path = tmp_path / "client.log"
    assert read_latest_snapshot(path) is None

    first = _snapshot(session_id="session-one", sequence=25)
    path.write_text(_line(first), encoding="utf-8")
    assert read_latest_snapshot(path) == first

    rotated = tmp_path / "client.log.1"
    path.replace(rotated)
    second = _snapshot(session_id="session-two", sequence=1, captured_at=200.0)
    path.write_text(_line(second), encoding="utf-8")
    latest = read_latest_snapshot(path)
    assert latest == second
    assert latest["session_id"] != first["session_id"]
    assert latest["sequence"] < first["sequence"]

    path.write_text("partial after truncation", encoding="utf-8")
    assert read_latest_snapshot(path) is None


def test_tail_read_is_bounded_and_discards_an_incomplete_first_line(tmp_path) -> None:
    path = tmp_path / "client.log"
    snapshot = _snapshot(sequence=8)
    path.write_text("x" * 2048 + "\n" + _line(snapshot), encoding="utf-8")

    assert read_latest_snapshot(path, max_bytes=1024) == snapshot


def test_freshness_uses_captured_at_and_only_forest_is_supported() -> None:
    snapshot = _snapshot(captured_at=100.0)
    assert freshness_status(snapshot, now=105.0) == ("live", 5.0)
    assert freshness_status(snapshot, now=108.0) == ("stale", 8.0)
    assert freshness_status(snapshot, now=108.0)[1] == pytest.approx(8.0)
    assert freshness_status(_snapshot(world_kind="cave"), now=100.0) == (
        "unsupported_world",
        0.0,
    )


def test_snapshot_validation_rejects_bad_version_ids_counts_and_nonfinite_values() -> None:
    assert validate_snapshot(_snapshot())["current"]["tile_types"] == ["FUTURE_TILE"]
    assert validate_snapshot(_snapshot())["directions"]["north"]["prefabs_seen"] == ["panflute"]

    mutations = [
        (lambda value: value.update(live_version=True), "live_version 1"),
        (lambda value: value.update(world_id=" " * 2), "world_id"),
        (lambda value: value.update(session_id="x" * 129), "session_id"),
        (lambda value: value.update(sequence=True), "sequence"),
        (lambda value: value.update(sequence=0), "sequence"),
        (lambda value: value.update(captured_at=float("nan")), "captured_at"),
        (lambda value: value.update(captured_at=10**1000), "captured_at"),
        (lambda value: value.update(camera_heading=float("inf")), "camera_heading"),
        (lambda value: value["position"].update(x=float("-inf")), "position.x"),
        (lambda value: value["position"].update(y=True), "position.y"),
        (lambda value: value["current"].update(prefab_counts={"mod_prefab": -1}), "non-negative integer"),
        (lambda value: value["directions"].update(sideways={}), "unknown direction"),
        (lambda value: value["landmarks"].append({"prefab": "panflute", "x": math.nan, "z": 0}), r"landmarks\[1\]\.x"),
    ]
    for mutate, message in mutations:
        bad = _snapshot()
        mutate(bad)
        with pytest.raises(LiveSnapshotError, match=message):
            validate_snapshot(bad)


def test_snapshot_validation_accepts_legacy_empty_and_populated_terrain() -> None:
    legacy = _snapshot()
    assert "terrain" not in validate_snapshot(legacy)

    empty = _snapshot(terrain={"tile_size": 4, "tiles": []})
    assert validate_snapshot(empty)["terrain"] == {"tile_size": 4, "tiles": []}

    populated = _snapshot(
        terrain={
            "tile_size": 4.0,
            "tiles": [
                {"x": -2.5, "z": 3, "tile": "DECIDUOUS"},
                {"x": 1, "z": 2, "tile": "GRASS", "passable": True},
                {"x": 3, "z": 4, "tile": "ROCKY", "passable": False},
            ],
        }
    )
    assert validate_snapshot(populated)["terrain"] == populated["terrain"]

    with_connections = _snapshot(
        terrain={
            "tile_size": 4,
            "tiles": [
                {
                    "x": 0,
                    "z": 0,
                    "tile": "GRASS",
                    "passable": True,
                    "connections": {"east": True, "north": False},
                },
                {"x": 4, "z": 0, "tile": "FOREST", "passable": True},
                {"x": 0, "z": 4, "tile": "ROCKY", "passable": True, "connections": {}},
            ],
        }
    )
    assert validate_snapshot(with_connections)["terrain"] == with_connections["terrain"]

    adjacent_large_coordinates = _snapshot(
        terrain={
            "tile_size": 4,
            "tiles": [
                {"x": 10**16, "z": 0, "tile": "GRASS"},
                {"x": 10**16 + 1, "z": 0, "tile": "FOREST"},
            ],
        }
    )
    assert len(validate_snapshot(adjacent_large_coordinates)["terrain"]["tiles"]) == 2


def test_snapshot_validation_accepts_player_anchor_and_legacy_omission(tmp_path) -> None:
    legacy = _snapshot()
    assert "player_anchor" not in validate_snapshot(legacy)

    anchored = _anchor_snapshot(
        {"x": 0, "z": 0, "clear": False},
        position=(-2, -2),
    )
    assert validate_snapshot(anchored)["player_anchor"] == {
        "x": 0,
        "z": 0,
        "clear": False,
    }

    path = tmp_path / "client.log"
    path.write_text(_line(anchored), encoding="utf-8")
    assert read_latest_snapshot(path) == anchored


def test_player_anchor_uses_half_open_bounds_and_adjacent_cell_at_upper_edge() -> None:
    lower_edge = _anchor_snapshot(
        {"x": 0, "z": 0, "clear": False},
        position=(-2, -2),
    )
    assert validate_snapshot(lower_edge)["player_anchor"]["clear"] is False

    upper_edge = _anchor_snapshot(
        {"x": 4, "z": 0, "clear": True},
        position=(2, 0),
        tiles=[
            {"x": 0, "z": 0, "tile": "GRASS", "passable": True},
            {"x": 4, "z": 0, "tile": "FOREST", "passable": True},
        ],
    )
    assert validate_snapshot(upper_edge)["player_anchor"]["x"] == 4

    excluded_upper_edge = _anchor_snapshot(
        {"x": 0, "z": 0, "clear": True},
        position=(2, 0),
    )
    with pytest.raises(LiveSnapshotError, match="unique passable tile containing position"):
        validate_snapshot(excluded_upper_edge)


@pytest.mark.parametrize(
    ("anchor", "message"),
    [
        (None, r"player_anchor must be a JSON object"),
        ([], r"player_anchor must be a JSON object"),
        ({"x": 0, "z": 0}, r"contain exactly x, z, and clear"),
        ({"x": 0, "z": 0, "clear": False, "extra": 1}, r"contain exactly x, z, and clear"),
        ({"x": True, "z": 0, "clear": False}, r"player_anchor.x must be a finite number"),
        ({"x": float("nan"), "z": 0, "clear": False}, r"player_anchor.x must be a finite number"),
        ({"x": 0, "z": float("inf"), "clear": False}, r"player_anchor.z must be a finite number"),
        ({"x": 10**1000, "z": 0, "clear": False}, r"player_anchor.x must be a finite number"),
        ({"x": 0, "z": 0, "clear": None}, r"player_anchor.clear must be a boolean"),
        ({"x": 0, "z": 0, "clear": 0}, r"player_anchor.clear must be a boolean"),
    ],
)
def test_snapshot_validation_rejects_malformed_player_anchor(anchor: object, message: str) -> None:
    with pytest.raises(LiveSnapshotError, match=message):
        validate_snapshot(_anchor_snapshot(anchor, position=(0, 0)))


def test_snapshot_validation_requires_anchor_to_be_the_unique_passable_cell_containing_player() -> None:
    snapshot_without_terrain = _snapshot()
    snapshot_without_terrain["player_anchor"] = {"x": 0, "z": 0, "clear": False}
    with pytest.raises(LiveSnapshotError, match="requires observed terrain"):
        validate_snapshot(snapshot_without_terrain)

    cases = [
        (
            _anchor_snapshot(
                {"x": 0, "z": 0, "clear": False},
                tiles=[],
            ),
            "must reference a passable terrain tile center",
        ),
        (
            _anchor_snapshot(
                {"x": 0, "z": 0, "clear": False},
                tiles=[{"x": 0, "z": 0, "tile": "GRASS", "passable": False}],
            ),
            "must reference a passable terrain tile center",
        ),
        (
            _anchor_snapshot(
                {"x": 0, "z": 0, "clear": False},
                tiles=[{"x": 0, "z": 0, "tile": "GRASS"}],
            ),
            "must reference a passable terrain tile center",
        ),
        (
            _anchor_snapshot(
                {"x": 4, "z": 0, "clear": False},
                tiles=[{"x": 0, "z": 0, "tile": "GRASS", "passable": True}],
            ),
            "must reference a passable terrain tile center",
        ),
        (
            _anchor_snapshot(
                {"x": 0, "z": 0, "clear": False},
                position=(2, 0),
            ),
            "unique passable tile containing position",
        ),
        (
            _anchor_snapshot(
                {"x": 0, "z": 0, "clear": False},
                position=(1, 0),
                tiles=[
                    {"x": 0, "z": 0, "tile": "GRASS", "passable": True},
                    {"x": 2, "z": 0, "tile": "FOREST", "passable": True},
                ],
            ),
            "unique passable tile containing position",
        ),
        (
            _anchor_snapshot(
                {"x": 4, "z": 0, "clear": False},
                position=(0, 0),
                tiles=[
                    {"x": 0, "z": 0, "tile": "GRASS", "passable": True},
                    {"x": 4, "z": 0, "tile": "FOREST", "passable": True},
                ],
            ),
            "unique passable tile containing position",
        ),
        (
            _anchor_snapshot(
                {"x": 1e100, "z": 0, "clear": False},
                position=(1e100, 0),
                tiles=[{"x": 1e100, "z": 0, "tile": "GRASS", "passable": True}],
            ),
            "unique passable tile containing position",
        ),
    ]
    for snapshot, message in cases:
        with pytest.raises(LiveSnapshotError, match=message):
            validate_snapshot(snapshot)


@pytest.mark.parametrize(
    ("terrain", "message"),
    [
        ({}, "terrain must contain exactly"),
        ({"tile_size": 4, "tiles": [], "extra": 1}, "terrain must contain exactly"),
        ({"tile_size": True, "tiles": []}, "terrain.tile_size"),
        ({"tile_size": 4.5, "tiles": []}, "terrain.tile_size must equal 4"),
        ({"tile_size": 4, "tiles": {}}, "terrain.tiles must be an array"),
        (
            {"tile_size": 4, "tiles": [{"x": index, "z": 0, "tile": "GRASS"} for index in range(257)]},
            "at most 256",
        ),
        ({"tile_size": 4, "tiles": [{"x": 0, "z": 0}]}, "contain x, z, and tile"),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "extra": 1}]},
            "only optional passable or connections",
        ),
        ({"tile_size": 4, "tiles": [{"x": True, "z": 0, "tile": "GRASS"}]}, r"terrain.tiles\[0\].x"),
        ({"tile_size": 4, "tiles": [{"x": 0, "z": float("nan"), "tile": "GRASS"}]}, r"terrain.tiles\[0\].z"),
        ({"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": " "}]}, r"terrain.tiles\[0\].tile"),
        ({"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "T" * 129}]}, "at most 128"),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "passable": None}]},
            r"terrain.tiles\[0\]\.passable must be a boolean",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "passable": 0}]},
            r"terrain.tiles\[0\]\.passable must be a boolean",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "passable": "false"}]},
            r"terrain.tiles\[0\]\.passable must be a boolean",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 1, "z": 2, "tile": "GRASS"}, {"x": 1.0, "z": 2, "tile": "FOREST"}]},
            "duplicate coordinate",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "connections": None}]},
            r"connections must be an object",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "connections": []}]},
            r"connections must be an object",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "connections": {"west": True}}]},
            r"only east and north",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "connections": {"east": 1}}]},
            r"connections.east must be a boolean",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "passable": False, "connections": {"east": False}}]},
            r"connections requires passable=true on this tile",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "connections": {"east": True}}, {"x": 4, "z": 0, "tile": "FOREST", "passable": True}]},
            r"connections requires passable=true on this tile",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "passable": True, "connections": {"east": False}}]},
            r"connections.east requires a distinct neighboring tile",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "passable": True, "connections": {"east": True}}, {"x": 4, "z": 0, "tile": "FOREST"}]},
            r"connections.east requires a distinct neighboring tile",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 0, "z": 0, "tile": "GRASS", "passable": True, "connections": {"east": False}}, {"x": 4, "z": 0, "tile": "FOREST", "passable": False}]},
            r"connections.east requires a distinct neighboring tile",
        ),
        (
            {"tile_size": 4, "tiles": [{"x": 1e100, "z": 0, "tile": "GRASS", "passable": True, "connections": {"east": True}}]},
            r"connections.east requires a distinct neighboring tile",
        ),
    ],
)
def test_snapshot_validation_rejects_malformed_terrain(terrain: dict, message: str) -> None:
    with pytest.raises(LiveSnapshotError, match=message):
        validate_snapshot(_snapshot(terrain=terrain))


def test_latest_snapshot_age_does_not_refresh_when_the_same_log_is_reread(tmp_path) -> None:
    path = tmp_path / "client.log"
    path.write_text(_line(_snapshot(captured_at=100.0)), encoding="utf-8")
    first_read = read_latest_snapshot(path)
    second_read = read_latest_snapshot(path)

    assert first_read == second_read
    assert freshness_status(first_read, now=104.0) == ("live", 4.0)
    assert freshness_status(second_read, now=109.0) == ("stale", 9.0)


def test_future_timestamp_cannot_keep_old_guidance_live() -> None:
    assert freshness_status(_snapshot(captured_at=101.0), now=100.0) == ("live", 0.0)
    with pytest.raises(LiveSnapshotError, match="ahead of the local clock"):
        freshness_status(_snapshot(captured_at=3700.0), now=100.0)
