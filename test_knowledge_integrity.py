"""Integrity checks for the curated default forest task/room graph."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from dst_route_planner.knowledge import build_forest_default_kb


AUDIT_PATH = Path(__file__).parent / "dst_route_planner" / "knowledge" / "source_audit.json"


def load_source_audit() -> dict:
    return json.loads(AUDIT_PATH.read_text(encoding="utf-8"))


def test_task_room_and_background_references_are_known_rooms() -> None:
    kb = build_forest_default_kb()
    missing_choices = {
        (task.name, room_name)
        for task in kb.tasks.values()
        for room_name in task.room_choices
        if room_name not in kb.rooms
    }
    missing_backgrounds = {
        (task.name, task.background_room)
        for task in kb.tasks.values()
        if task.background_room not in kb.rooms
    }

    assert not missing_choices, f"Unknown task room choices: {sorted(missing_choices)}"
    assert not missing_backgrounds, f"Unknown task background rooms: {sorted(missing_backgrounds)}"


def test_target_chains_reference_known_tasks_rooms_and_layouts() -> None:
    kb = build_forest_default_kb()
    mismatched_targets = []
    missing_tasks = []
    missing_rooms = []
    missing_layouts = []

    for target_prefab, chains in kb.target_chains.items():
        for chain in chains:
            if chain.target_prefab != target_prefab:
                mismatched_targets.append((target_prefab, chain.target_prefab))
            if chain.task not in kb.tasks:
                missing_tasks.append((target_prefab, chain.task))
            if chain.room and chain.room not in kb.rooms:
                missing_rooms.append((target_prefab, chain.room))
            if chain.static_layout and chain.static_layout not in kb.static_layouts:
                missing_layouts.append((target_prefab, chain.static_layout))

    assert not mismatched_targets, f"Target-chain prefab keys disagree: {mismatched_targets}"
    assert not missing_tasks, f"Unknown target-chain tasks: {missing_tasks}"
    assert not missing_rooms, f"Unknown target-chain rooms: {missing_rooms}"
    assert not missing_layouts, f"Unknown target-chain static layouts: {missing_layouts}"


def test_room_static_layout_references_are_defined() -> None:
    kb = build_forest_default_kb()
    missing = {
        (room.name, layout_name)
        for room in kb.rooms.values()
        for layout_name in room.countstaticlayouts
        if layout_name not in kb.static_layouts
    }
    assert not missing, f"Unknown room static layouts: {sorted(missing)}"


def test_added_rooms_preserve_lua_backed_discriminators() -> None:
    kb = build_forest_default_kb()

    # Sources: scripts/map/rooms/forest/terrain_forest.lua and
    # scripts/map/rooms/forest/terrain_noise.lua.
    critter_den = kb.rooms["CritterDen"]
    assert critter_den.tile == "GROUND_NOISE"
    assert critter_den.countprefabs["critterlab"] == 1

    bg_noise = kb.rooms["BGNoise"]
    assert bg_noise.tile == "GROUND_NOISE"
    assert bg_noise.countprefabs["deerspawningground"] == 1
    assert {"ExitPiece", "Chester_Eyebone"} <= bg_noise.tags
    assert bg_noise.distributeprefabs["evergreen"] == 1.5

    # Source: scripts/map/rooms/forest/DLCrooms.lua. The Astral tags and
    # different molehill densities distinguish the two deciduous mole rooms.
    deciduous_mole = kb.rooms["DeciduousMole"]
    molesville = kb.rooms["MolesvilleDeciduous"]
    assert deciduous_mole.tile == molesville.tile == "DECIDUOUS"
    assert "Astral_1" in deciduous_mole.tags
    assert "Astral_2" in molesville.tags
    assert deciduous_mole.distributeprefabs["molehill"] == 0.5
    assert molesville.distributeprefabs["molehill"] == 0.7

    deciduous_clearing = kb.rooms["DeciduousClearing"]
    assert deciduous_clearing.tile == "DECIDUOUS"
    assert "Astral_1" in deciduous_clearing.tags
    assert deciduous_clearing.distributeprefabs["deciduoustree"] == 1
    assert deciduous_clearing.distributeprefabs["red_mushroom"] == 0.5


def test_source_audit_covers_the_curated_mainland_slice() -> None:
    kb = build_forest_default_kb()
    audit = load_source_audit()
    mapped_rooms = [name for names in audit["room_sources"].values() for name in names]

    assert len(kb.rooms) == audit["coverage"]["rooms"] == 53
    assert len(mapped_rooms) == len(set(mapped_rooms))
    assert set(mapped_rooms) == set(kb.rooms)
    assert set(audit["room_tiles"]) == set(kb.rooms)
    assert len(kb.tasks) == audit["coverage"]["tasks"] == 20
    assert set(audit["task_fields"]) == set(kb.tasks)
    assert len(kb.static_layouts) == audit["coverage"]["static_layouts"] == 13
    assert len(kb.target_chains) == audit["coverage"]["target_prefabs"] == 20
    assert set(audit["static_layout_sources"]) == set(kb.static_layouts)
    assert {
        name: layout.source for name, layout in kb.static_layouts.items()
    } == audit["static_layout_sources"]
    for name, prefabs in audit["static_layout_prefabs"].items():
        assert kb.static_layouts[name].prefabs == frozenset(prefabs)

    # Provenance stays portable: the test validates the checked-in manifest
    # and never needs access to the local game source tree.
    assert set(audit["room_sources"]) <= set(audit["files"])
    assert audit["task_source"] in audit["files"]
    assert audit["size_variation"]["source"] in audit["files"]
    assert "map/layouts.lua" in audit["files"]
    for source in audit["static_layout_sources"].values():
        assert source.removeprefix("scripts/") in audit["files"], source
    for path, digest in audit["files"].items():
        assert not Path(path).is_absolute(), path
        assert "\\" not in path, path
        assert re.fullmatch(r"[0-9a-f]{64}", digest), path


def test_all_room_tiles_match_the_pinned_source_values() -> None:
    kb = build_forest_default_kb()
    expected = load_source_audit()["room_tiles"]

    mismatches = {
        name: (expected_tile, kb.rooms[name].tile)
        for name, expected_tile in expected.items()
        if kb.rooms[name].tile != expected_tile
    }
    assert not mismatches, f"Room tile values differ from source audit: {mismatches}"


def test_task_fields_and_expected_random_choices_match_the_audit() -> None:
    kb = build_forest_default_kb()
    audit = load_source_audit()
    dynamic = audit["dynamic_task_choices"]
    expected_dynamic_keys = set()

    assert audit["size_variation"]["value"] == 3
    for name, source_fields in audit["task_fields"].items():
        task = kb.tasks[name]
        assert task.required is source_fields["required"], name
        assert task.locks == tuple(source_fields["locks"]), name
        assert task.keys_given == tuple(source_fields["keys_given"]), name
        assert task.room_bg == source_fields["room_bg"], name
        assert task.background_room == source_fields["background_room"], name

        expected_choices = dict(source_fields["fixed_room_choices"])
        for room_name in source_fields["dynamic_room_choices"]:
            key = f"{name}.{room_name}"
            expected_dynamic_keys.add(key)
            expected_choices[room_name] = dynamic[key]["expected"]
        assert set(task.room_choices) == set(expected_choices), name
        for room_name, expected_count in expected_choices.items():
            assert task.room_choices[room_name] == pytest.approx(expected_count), (name, room_name)

    assert expected_dynamic_keys == set(dynamic)


def test_source_backed_room_values_use_fixed_counts_or_expected_values() -> None:
    kb = build_forest_default_kb()
    audit = load_source_audit()

    for room_name, fields in audit["fixed_room_values"].items():
        room = kb.rooms[room_name]
        for field_name, expected in fields.items():
            actual = getattr(room, field_name)
            if isinstance(expected, list):
                assert set(actual) >= set(expected), (room_name, field_name)
            else:
                for prefab, expected_value in expected.items():
                    assert actual[prefab] == pytest.approx(expected_value), (room_name, field_name, prefab)

    for key, source_value in audit["dynamic_room_counts"].items():
        room_name, prefab = key.rsplit(".", 1)
        values = getattr(kb.rooms[room_name], source_value["represented_as"])
        assert values[prefab] == pytest.approx(source_value["expected"]), key
