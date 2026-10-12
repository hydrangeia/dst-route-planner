#!/usr/bin/env python
"""Precision checks for static-layout evidence and direct target visibility."""

from __future__ import annotations

from collections import Counter

from dst_route_planner.inference import initial_belief, score_rooms, score_tasks
from dst_route_planner.knowledge import build_forest_default_kb
from dst_route_planner.models import Direction, DirectionObservation, Observation
from dst_route_planner.navigation import probabilities_by_direction, rank_directions


kb = build_forest_default_kb()


def make_observation(tile_types: list[str], prefabs: list[str], *, connection_like: bool | None = None, background_like: bool | None = None) -> Observation:
    counts = Counter(prefabs)
    return Observation(
        tile_types=frozenset(tile_types),
        prefabs_seen=frozenset(counts),
        prefab_counts=counts,
        connection_like=connection_like,
        background_like=background_like,
    )


def assert_top_room(name: str, obs: Observation, expected: str) -> None:
    room_probs = score_rooms(kb, obs)
    top = sorted(room_probs.items(), key=lambda item: item[1], reverse=True)[:3]
    print(f"\n{name}")
    for room, prob in top:
        print(f"  {room:30s}: {prob:.4f}")
    assert top[0][0] == expected, f"{name}: expected {expected}, got {top[0][0]}"


def test_static_layout_prefabs_identify_rooms() -> None:
    assert_top_room(
        "Panflute implies MagicalDeciduous through DeciduousPond",
        make_observation([], ["panflute"]),
        "MagicalDeciduous",
    )
    assert_top_room(
        "Moonbase implies MoonbaseOne through static layout",
        make_observation([], ["moonbase"]),
        "MoonbaseOne",
    )
    assert_top_room(
        "Oasis lake implies LightningBluffOasis through static layout",
        make_observation([], ["oasislake"]),
        "LightningBluffOasis",
    )


def test_task_context_density_uses_common_prefabs() -> None:
    glommer_room = score_rooms(
        kb,
        make_observation(["DECIDUOUS"], ["flower", "flower", "fireflies", "molehill", "deciduoustree"]),
    )
    deep_room = score_rooms(
        kb,
        make_observation(["DECIDUOUS"], ["deciduoustree", "deciduoustree", "fireflies", "catcoonden"]),
    )

    print("\nTask-context density evidence")
    print(f"  MagicalDeciduous from flower/fireflies/molehill: {glommer_room['MagicalDeciduous']:.4f}")
    print(f"  DeepDeciduous from trees/fireflies/catcoon:      {deep_room['DeepDeciduous']:.4f}")

    assert glommer_room["MagicalDeciduous"] > glommer_room["DeepDeciduous"] * 2
    assert deep_room["DeepDeciduous"] > deep_room["MagicalDeciduous"]


def test_known_prefab_absence_can_discriminate_rooms() -> None:
    # The local view crosses a grass/forest edge: MandrakeHome itself is GRASS,
    # while MoonbaseOne is FOREST. Preserve both observed tile types.
    obs = make_observation(["GRASS", "FOREST"], ["blue_mushroom", "evergreen", "sapling"])
    room_probs = score_rooms(kb, obs)
    task_probs, _ = score_tasks(kb, obs)

    print("\nKnown-prefab absence evidence")
    print(f"  MoonbaseOne:      {room_probs['MoonbaseOne']:.4f}")
    print(f"  MandrakeHome:     {room_probs['MandrakeHome']:.4f}")
    print(f"  Forest hunters:   {task_probs['Forest hunters']:.4f}")
    print(f"  For a nice walk:  {task_probs['For a nice walk']:.4f}")

    assert room_probs["MoonbaseOne"] > room_probs["MandrakeHome"] * 100
    assert room_probs["MoonbaseOne"] > room_probs["Forest"] * 10
    assert task_probs["Forest hunters"] > task_probs["For a nice walk"] * 4


def test_hard_exclusions_remove_impossible_room_matches() -> None:
    obs = make_observation(["FOREST"], ["moonbase", "evergreen", "sapling"])
    room_probs = score_rooms(kb, obs)

    print("\nHard exclusion evidence")
    print(f"  MoonbaseOne:      {room_probs['MoonbaseOne']:.4f}")
    print(f"  MandrakeHome:     {room_probs['MandrakeHome']:.6f}")
    print(f"  PigVillage:       {room_probs['PigVillage']:.6f}")

    assert room_probs["MoonbaseOne"] > 0.80
    assert room_probs["MandrakeHome"] < 0.001
    assert room_probs["PigVillage"] < 0.001


def test_strong_exclusions_support_same_tile_negative_reasoning() -> None:
    # Both MoonbaseOne and DeepForest use FOREST. The juicy berrybush cue is
    # directly listed for MoonbaseOne and distinguishes it from DeepForest.
    obs = make_observation(["FOREST"], ["blue_mushroom", "green_mushroom", "evergreen", "berrybush_juicy"])
    room_probs = score_rooms(kb, obs)

    print("\nStrong same-tile exclusion evidence")
    print(f"  MoonbaseOne:      {room_probs['MoonbaseOne']:.4f}")
    print(f"  MandrakeHome:     {room_probs['MandrakeHome']:.6f}")
    print(f"  DeepForest:       {room_probs['DeepForest']:.6f}")

    assert room_probs["MoonbaseOne"] > room_probs["MandrakeHome"] * 200
    assert room_probs["MoonbaseOne"] > room_probs["DeepForest"] * 100


def test_soft_exclusions_do_not_override_direct_target_evidence() -> None:
    obs = make_observation(["GRASS"], ["mandrake_planted", "flower", "spiderden"])
    room_probs = score_rooms(kb, obs)

    print("\nSoft exclusion keeps direct target evidence")
    print(f"  MandrakeHome:     {room_probs['MandrakeHome']:.4f}")
    print(f"  SpiderVillage:    {room_probs['SpiderVillage']:.4f}")
    print(f"  MoonbaseOne:      {room_probs['MoonbaseOne']:.6f}")

    assert room_probs["MandrakeHome"] > 0.55
    assert room_probs["MandrakeHome"] > room_probs["SpiderVillage"] * 3
    assert room_probs["MandrakeHome"] > room_probs["MoonbaseOne"] * 100


def test_visible_target_direction_wins() -> None:
    belief = initial_belief(kb)
    observations = [
        DirectionObservation(
            Direction.NORTH,
            make_observation(["DECIDUOUS"], ["deciduoustree", "fireflies", "flower"], connection_like=True, background_like=False),
        ),
        DirectionObservation(
            Direction.SOUTH,
            make_observation(["FOREST"], ["panflute"], connection_like=False, background_like=True),
        ),
    ]

    scores = rank_directions(kb, "panflute", belief, observations)
    probs = probabilities_by_direction(scores)
    print("\nVisible panflute direction ranking")
    for score in scores:
        print(f"  {score.direction.value:10s}: score={score.score:.4f} p_dir={probs[score.direction.value]:.4f}")
        print(f"    {'; '.join(score.explanation)}")

    assert scores[0].direction is Direction.SOUTH
    assert probs["south"] > 0.70
    assert any("target prefab visible" in explanation for explanation in scores[0].explanation)


if __name__ == "__main__":
    test_static_layout_prefabs_identify_rooms()
    test_task_context_density_uses_common_prefabs()
    test_known_prefab_absence_can_discriminate_rooms()
    test_hard_exclusions_remove_impossible_room_matches()
    test_strong_exclusions_support_same_tile_negative_reasoning()
    test_soft_exclusions_do_not_override_direct_target_evidence()
    test_visible_target_direction_wins()
    print("\nPhase 7 precision checks passed.")
