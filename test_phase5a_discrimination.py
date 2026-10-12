#!/usr/bin/env python
"""Regression checks for room discrimination and prefab-count evidence."""

from __future__ import annotations

from collections import Counter

from dst_route_planner.inference import score_rooms
from dst_route_planner.io import observation_from_dict
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


def ranked_targets(obs: Observation, targets: list[str]) -> list[tuple[str, float]]:
    room_probs = score_rooms(kb, obs)
    results = [(room, room_probs.get(room, 0.0)) for room in targets]
    return sorted(results, key=lambda item: item[1], reverse=True)


def assert_top(name: str, obs: Observation, expected: str, targets: list[str]) -> None:
    results = ranked_targets(obs, targets)
    print(f"\n{name}")
    for room, prob in results:
        print(f"  {room:30s}: {prob:.4f}")
    actual = results[0][0]
    assert actual == expected, f"{name}: expected {expected}, got {actual}"


def assert_greater(name: str, obs: Observation, better: str, worse: str) -> None:
    room_probs = score_rooms(kb, obs)
    print(f"\n{name}")
    print(f"  {better:30s}: {room_probs.get(better, 0.0):.4f}")
    print(f"  {worse:30s}: {room_probs.get(worse, 0.0):.4f}")
    assert room_probs[better] > room_probs[worse], f"{name}: expected {better} > {worse}"


def test_discrimination_cases() -> None:
    assert_greater(
        "Pig village evidence should beat PigKingdom when pigking is absent",
        make_observation(["FOREST"], ["pighouse", "evergreen", "sapling"]),
        "PigVillage",
        "PigKingdom",
    )

    assert_top(
        "Pig king evidence",
        make_observation(["GRASS"], ["pigking", "pighouse"]),
        "PigKingdom",
        ["PigVillage", "PigKingdom", "PigTown"],
    )

    assert_top(
        "MagicalDeciduous evidence",
        make_observation(["DECIDUOUS"], ["flower", "fireflies", "molehill", "deciduoustree"]),
        "MagicalDeciduous",
        ["MagicalDeciduous", "DeepDeciduous", "BGDeciduous"],
    )

    assert_top(
        "DeepDeciduous evidence",
        make_observation(["DECIDUOUS"], ["deciduoustree", "fireflies", "catcoonden"]),
        "DeepDeciduous",
        ["MagicalDeciduous", "DeepDeciduous", "BGDeciduous"],
    )

    assert_top(
        "MandrakeHome evidence",
        make_observation(["FOREST"], ["flower", "evergreen", "fireflies"]),
        "MandrakeHome",
        ["MandrakeHome", "MoonbaseOne", "Forest"],
    )

    assert_top(
        "MoonbaseOne minimal evidence",
        make_observation(["FOREST"], ["evergreen", "sapling", "grass"]),
        "MoonbaseOne",
        ["MandrakeHome", "MoonbaseOne", "Forest"],
    )

    assert_top(
        "BeeQueenBee hive cluster evidence",
        make_observation(["GRASS"], ["flower", "flower", "flower", "beehive", "wasphive"]),
        "BeeQueenBee",
        ["BeeQueenBee", "BeeClearing", "Clearing"],
    )


def test_json_prefab_counts_preserve_duplicates() -> None:
    obs = observation_from_dict(
        {
            "tile_types": ["GRASS"],
            "prefabs_seen": ["flower", "flower", "flower", "beehive"],
        }
    )

    assert obs.prefabs_seen == frozenset({"flower", "beehive"})
    assert obs.prefab_counts["flower"] == 3
    assert obs.prefab_counts["beehive"] == 1


if __name__ == "__main__":
    test_discrimination_cases()
    test_json_prefab_counts_preserve_duplicates()
    print("\nPhase 5b discrimination checks passed.")
