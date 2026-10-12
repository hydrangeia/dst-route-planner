#!/usr/bin/env python
"""Task-level blacklist checks for taskset setpieces."""

from __future__ import annotations

from collections import Counter

from dst_route_planner.inference import score_tasks
from dst_route_planner.knowledge import build_forest_default_kb
from dst_route_planner.models import Observation


kb = build_forest_default_kb()


def make_observation(prefabs: list[str]) -> Observation:
    counts = Counter(prefabs)
    return Observation(prefabs_seen=frozenset(counts), prefab_counts=counts)


def task_mass(task_probs: dict[str, float], tasks: set[str]) -> float:
    return sum(prob for task, prob in task_probs.items() if task in tasks)


def print_top(name: str, task_probs: dict[str, float]) -> None:
    print(f"\n{name}")
    for task, prob in sorted(task_probs.items(), key=lambda item: item[1], reverse=True)[:8]:
        print(f"  {task:24s}: {prob:.4f}")


def test_cave_entrance_uses_default_taskset_whitelist() -> None:
    allowed = {
        "Make a pick",
        "Dig that rock",
        "Great Plains",
        "Squeltch",
        "Beeeees!",
        "Speak to the king",
        "Forest hunters",
        "Befriend the pigs",
        "For a nice walk",
        "Kill the spiders",
        "Killer bees!",
        "Make a Beehat",
        "The hunters",
        "Magic meadow",
        "Frogs and bugs",
    }
    task_probs, _ = score_tasks(kb, make_observation(["cave_entrance"]))

    print_top("Cave entrance taskset blacklist evidence", task_probs)
    assert task_mass(task_probs, allowed) > 0.95
    assert task_probs["Badlands"] < 0.01
    assert task_probs["Lightning Bluff"] < 0.01


def test_resurrectionstone_uses_default_taskset_whitelist() -> None:
    allowed = {
        "Make a pick",
        "Dig that rock",
        "Great Plains",
        "Squeltch",
        "Beeeees!",
        "Speak to the king",
        "Forest hunters",
        "Badlands",
    }
    task_probs, _ = score_tasks(kb, make_observation(["resurrectionstone"]))

    print_top("Resurrection stone taskset blacklist evidence", task_probs)
    assert task_mass(task_probs, allowed) > 0.90
    assert task_probs["For a nice walk"] < 0.01
    assert task_probs["Lightning Bluff"] < 0.01


def test_wormhole_uses_default_taskset_whitelist() -> None:
    allowed = {
        "Make a pick",
        "Dig that rock",
        "Great Plains",
        "Squeltch",
        "Beeeees!",
        "Speak to the king",
        "Forest hunters",
        "Befriend the pigs",
        "For a nice walk",
        "Kill the spiders",
        "Killer bees!",
        "Make a Beehat",
        "The hunters",
        "Magic meadow",
        "Frogs and bugs",
        "Badlands",
    }
    task_probs, _ = score_tasks(kb, make_observation(["wormhole"]))

    print_top("Wormhole taskset blacklist evidence", task_probs)
    assert task_mass(task_probs, allowed) > 0.95
    assert task_probs["Lightning Bluff"] < 0.01
    assert task_probs["Mole Colony Rocks"] < 0.01
    assert task_probs["MooseBreedingTask"] < 0.01


def test_single_moose_nest_uses_taskset_blacklist() -> None:
    allowed = {
        "Make a pick",
        "Beeeees!",
        "Speak to the king",
        "Forest hunters",
        "Befriend the pigs",
        "For a nice walk",
        "Make a Beehat",
        "Magic meadow",
        "Frogs and bugs",
    }
    task_probs, _ = score_tasks(kb, make_observation(["moose_nesting_ground"]))

    print_top("Single moose nest taskset blacklist evidence", task_probs)
    assert task_mass(task_probs, allowed) > 0.85
    assert task_probs["MooseBreedingTask"] < 0.01
    assert task_probs["Badlands"] < 0.01
    assert task_probs["Lightning Bluff"] < 0.01


def test_four_moose_nests_identify_moose_breeding_task() -> None:
    task_probs, room_probs = score_tasks(
        kb,
        make_observation([
            "moose_nesting_ground",
            "moose_nesting_ground",
            "moose_nesting_ground",
            "moose_nesting_ground",
        ]),
    )

    print_top("Four moose nests breeding task evidence", task_probs)
    print(f"  MooseGooseBreedingGrounds room: {room_probs['MooseGooseBreedingGrounds']:.4f}")
    assert task_probs["MooseBreedingTask"] > 0.80
    assert room_probs["MooseGooseBreedingGrounds"] > 0.80


if __name__ == "__main__":
    test_cave_entrance_uses_default_taskset_whitelist()
    test_resurrectionstone_uses_default_taskset_whitelist()
    test_wormhole_uses_default_taskset_whitelist()
    test_single_moose_nest_uses_taskset_blacklist()
    test_four_moose_nests_identify_moose_breeding_task()
    print("\nPhase 8 task feature checks passed.")
