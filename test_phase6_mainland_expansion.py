#!/usr/bin/env python
"""Regression checks for the expanded default mainland knowledge slice."""

from __future__ import annotations

from collections import Counter

from dst_route_planner.inference import score_rooms
from dst_route_planner.knowledge import build_forest_default_kb
from dst_route_planner.models import Observation


kb = build_forest_default_kb()


def make_observation(tile_types: list[str], prefabs: list[str]) -> Observation:
    counts = Counter(prefabs)
    return Observation(
        tile_types=frozenset(tile_types),
        prefabs_seen=frozenset(counts),
        prefab_counts=counts,
    )


def assert_top_room(name: str, obs: Observation, expected: str) -> None:
    room_probs = score_rooms(kb, obs)
    top = sorted(room_probs.items(), key=lambda item: item[1], reverse=True)[:3]
    print(f"\n{name}")
    for room, prob in top:
        print(f"  {room:30s}: {prob:.4f}")
    assert top[0][0] == expected, f"{name}: expected {expected}, got {top[0][0]}"


def test_expanded_mainland_rooms() -> None:
    assert_top_room(
        "Dragonfly arena evidence",
        make_observation(["DIRT_NOISE"], ["dragonfly_spawner", "cactus", "houndbone"]),
        "DragonflyArena",
    )
    assert_top_room(
        "Lightning goat desert evidence",
        make_observation(["DIRT_NOISE"], ["lightninggoat", "lightninggoat", "oasis_cactus"]),
        "LightningBluffLightning",
    )
    assert_top_room(
        "Oasis evidence",
        make_observation(["DIRT_NOISE"], ["oasislake", "oasis_cactus", "houndbone"]),
        "LightningBluffOasis",
    )
    assert_top_room(
        "Moose goose breeding evidence",
        make_observation(["GRASS"], ["moose_nesting_ground", "moose_nesting_ground", "moose_nesting_ground", "moose_nesting_ground", "grass", "sapling"]),
        "MooseGooseBreedingGrounds",
    )
    assert_top_room(
        "Rocky spider village evidence",
        make_observation(["ROCKY"], ["spiderden", "spiderden", "rock1", "rock2"]),
        "SpiderVillage",
    )
    assert_top_room(
        "Mermy swamp evidence",
        make_observation(["MARSH"], ["mermhouse", "tentacle", "marsh_tree", "marsh_bush"]),
        "SlightlyMermySwamp",
    )
    assert_top_room(
        "Killer bee nest evidence",
        make_observation(["GRASS"], ["wasphive", "wasphive", "flower", "flower", "grass"]),
        "Waspnests",
    )


def test_default_mainland_task_coverage() -> None:
    expected_tasks = {
        "Squeltch",
        "Badlands",
        "Lightning Bluff",
        "Kill the spiders",
        "Killer bees!",
        "Make a Beehat",
        "The hunters",
        "Frogs and bugs",
        "Mole Colony Rocks",
        "MooseBreedingTask",
    }
    assert expected_tasks.issubset(kb.tasks)

    expected_targets = {
        "dragonfly_spawner",
        "antlion_spawner",
        "oasislake",
        "lightninggoat",
        "moose_nesting_ground",
        "spiderden",
        "wasphive",
        "mermhouse",
        "tentacle",
        "molehill",
    }
    assert expected_targets.issubset(kb.target_chains)


if __name__ == "__main__":
    test_expanded_mainland_rooms()
    test_default_mainland_task_coverage()
    print("\nPhase 6 mainland expansion checks passed.")
