"""Integrity checks for the curated default forest task/room graph."""

from __future__ import annotations

from dst_route_planner.knowledge import build_forest_default_kb


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
