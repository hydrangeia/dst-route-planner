from __future__ import annotations

import math
from collections import defaultdict

from dst_route_planner.models import BeliefState, KnowledgeBase, Observation, RoomDef, TaskDef


def normalize(scores: dict[str, float], floor: float = 1e-9) -> dict[str, float]:
    cleaned = {k: max(float(v), floor) for k, v in scores.items()}
    total = sum(cleaned.values())
    if total <= 0:
        n = max(len(cleaned), 1)
        return {k: 1.0 / n for k in cleaned}
    return {k: v / total for k, v in cleaned.items()}


def initial_belief(kb: KnowledgeBase) -> BeliefState:
    task_scores: dict[str, float] = {}
    for task in kb.tasks.values():
        if task.name in kb.start_tasks:
            task_scores[task.name] = 6.0
        elif task.required:
            task_scores[task.name] = 2.0
        else:
            task_scores[task.name] = max(task.optional_weight, 0.5)

    room_scores: dict[str, float] = {room.name: 1.0 for room in kb.rooms.values()}
    for start in kb.start_tasks:
        task = kb.tasks[start]
        for room, count in task.room_choices.items():
            room_scores[room] = room_scores.get(room, 1.0) + count
    return BeliefState(normalize(task_scores), normalize(room_scores), known_keys=frozenset({"NONE"}))


def infer_known_keys(kb: KnowledgeBase, task_probs: dict[str, float], threshold: float = 0.35) -> frozenset[str]:
    keys = {"NONE"}
    for task_name, prob in task_probs.items():
        if prob >= threshold:
            keys.update(kb.tasks[task_name].keys_given)
    return frozenset(keys)


def _tile_likelihood(room: RoomDef, obs: Observation) -> float:
    if not obs.tile_types:
        return 1.0
    if room.tile in obs.tile_types:
        return 4.0
    return 0.45


def _prefab_counts(obs: Observation) -> dict[str, int]:
    counts = {prefab: int(count) for prefab, count in obs.prefab_counts.items() if int(count) > 0}
    for prefab in obs.prefabs_seen:
        counts.setdefault(prefab, 1)
    return counts


def _count_boost(base_multiplier: float, count: int, expected_density: float | None = None) -> float:
    if count <= 1:
        return base_multiplier
    extra_seen = min(count - 1, 4)
    multiplier = base_multiplier * (1.0 + 0.25 * extra_seen)
    if expected_density and expected_density > 0:
        density_ratio = min(count / expected_density, 1.5)
        multiplier *= 1.0 + 0.35 * density_ratio
    return multiplier


def _count_matches_chain(chain, count: int) -> bool:
    return count >= chain.min_count and (chain.max_count <= 0 or count <= chain.max_count)


def _static_layout_prefabs(kb: KnowledgeBase, room: RoomDef) -> dict[str, float]:
    direct_room_prefabs: set[str] = set()
    for known_room in kb.rooms.values():
        direct_room_prefabs.update(known_room.required_prefabs)
        direct_room_prefabs.update(known_room.countprefabs)
        direct_room_prefabs.update(known_room.distributeprefabs)

    prefabs: dict[str, float] = {}
    for layout_name, layout_count in room.countstaticlayouts.items():
        layout = kb.static_layouts.get(layout_name)
        if not layout:
            continue
        for prefab in layout.prefabs:
            if prefab in direct_room_prefabs:
                continue
            prefabs[prefab] = prefabs.get(prefab, 0.0) + float(layout_count)
    return prefabs


def _room_prefab_density(room: RoomDef, prefab: str) -> float:
    if prefab in room.required_prefabs:
        return 12.0
    if prefab in room.countprefabs:
        return float(room.countprefabs[prefab])
    if prefab in room.distributeprefabs:
        return float(room.distributeprefabs[prefab])
    return 0.0


def _task_context_density_bonus(kb: KnowledgeBase, room: RoomDef, prefab: str, density: float) -> float:
    """Boost prefabs that are unusually dense inside this room's task context."""
    if density <= 0:
        return 1.0

    sibling_densities: list[float] = []
    for task in kb.tasks.values():
        if room.name not in task.room_choices:
            continue
        for sibling_name in task.room_choices:
            if sibling_name == room.name:
                continue
            sibling = kb.rooms.get(sibling_name)
            if sibling:
                sibling_densities.append(_room_prefab_density(sibling, prefab))

    if not sibling_densities:
        return 1.0

    sibling_max = max(sibling_densities)
    sibling_avg = sum(sibling_densities) / len(sibling_densities)
    if sibling_max <= 0:
        return 1.6

    contrast = density / max(sibling_avg, 0.1)
    if density > sibling_max:
        return min(1.0 + 0.25 * contrast, 1.7)
    if density >= sibling_max * 0.75:
        return 1.15
    return 1.0


def _tile_context_density_bonus(kb: KnowledgeBase, room: RoomDef, prefab: str, density: float, obs: Observation) -> float:
    if density <= 0 or room.tile not in obs.tile_types:
        return 1.0

    same_tile_densities = [
        _room_prefab_density(known_room, prefab)
        for known_room in kb.rooms.values()
        if known_room.name != room.name and known_room.tile == room.tile
    ]
    same_tile_max = max(same_tile_densities, default=0.0)
    same_tile_positive = sum(1 for value in same_tile_densities if value > 0)
    if same_tile_max <= 0:
        return 2.0
    if density > same_tile_max:
        return 1.5
    if density > 0 and same_tile_positive <= 2:
        return 1.3
    return 1.0


def _known_prefab_absence_penalty(kb: KnowledgeBase, room: RoomDef, prefab: str, obs: Observation) -> float:
    """Discount rooms that omit a known prefab seen in another comparable room."""
    if prefab in room.negative_prefabs:
        return 1.0
    if _room_prefab_density(room, prefab) > 0:
        return 1.0

    if room.tile in obs.tile_types:
        same_tile_has_prefab = any(
            known_room.name != room.name
            and known_room.tile == room.tile
            and _room_prefab_density(known_room, prefab) > 0
            for known_room in kb.rooms.values()
        )
        if same_tile_has_prefab:
            return 0.30

    known_densities = [
        _room_prefab_density(known_room, prefab)
        for known_room in kb.rooms.values()
        if known_room.name != room.name
    ]
    max_known_density = max(known_densities, default=0.0)
    if max_known_density <= 0:
        return 0.85

    sibling_has_prefab = False
    sibling_count = 0
    for task in kb.tasks.values():
        if room.name not in task.room_choices:
            continue
        for sibling_name in task.room_choices:
            if sibling_name == room.name:
                continue
            sibling = kb.rooms.get(sibling_name)
            if not sibling:
                continue
            sibling_count += 1
            if _room_prefab_density(sibling, prefab) > 0:
                sibling_has_prefab = True

    if sibling_has_prefab:
        return 0.45
    if sibling_count:
        return 0.65
    return 0.75


def _prefab_likelihood(kb: KnowledgeBase, room: RoomDef, obs: Observation) -> float:
    prefab_counts = _prefab_counts(obs)
    if not prefab_counts:
        return 1.0
    score = 1.0
    static_layout_prefabs = _static_layout_prefabs(kb, room)
    all_room_prefabs = set(room.required_prefabs)
    all_room_prefabs.update(room.countprefabs)
    all_room_prefabs.update(room.distributeprefabs)
    all_room_prefabs.update(room.countstaticlayouts)
    all_room_prefabs.update(static_layout_prefabs)
    for prefab, count in prefab_counts.items():
        if prefab in room.prefab_exclusions:
            score *= room.prefab_exclusions[prefab] ** min(count, 2)
        elif prefab in room.negative_prefabs:
            score *= 0.15 ** min(count, 2)
        elif prefab in room.required_prefabs:
            score *= _count_boost(20.0, count)
        elif prefab in room.countprefabs:
            min_count = room.min_prefab_counts.get(prefab, 1)
            if count < min_count:
                score *= 0.20 ** (min_count - count)
            else:
                base_multiplier = 24.0 if min_count > 1 else 8.0
                score *= _count_boost(base_multiplier, count, room.countprefabs[prefab])
        elif prefab in room.countstaticlayouts:
            score *= _count_boost(8.0, count, room.countstaticlayouts[prefab])
        elif prefab in room.distributeprefabs:
            base_mult = 2.0 + min(room.distributeprefabs[prefab], 10.0) / 4.0
            density = room.distributeprefabs[prefab]
            if prefab in room.prefab_weights:
                expected_density = room.prefab_weights[prefab]
                density_bonus = min(density / expected_density if expected_density > 0 else 1.0, 2.0)
                base_mult *= (1.0 + density_bonus) / 2.0
            base_mult *= _task_context_density_bonus(kb, room, prefab, density)
            base_mult *= _tile_context_density_bonus(kb, room, prefab, density, obs)
            score *= _count_boost(base_mult, count, density)
        elif prefab in static_layout_prefabs:
            score *= _count_boost(14.0, count, static_layout_prefabs[prefab])
        elif prefab in all_room_prefabs:
            score *= _count_boost(2.0, count)
        else:
            score *= _known_prefab_absence_penalty(kb, room, prefab, obs) ** min(count, 3)

    for prefab in room.required_prefabs:
        if prefab not in prefab_counts:
            score *= 0.3

    return score


def score_rooms(kb: KnowledgeBase, obs: Observation, prior: dict[str, float] | None = None) -> dict[str, float]:
    scores: dict[str, float] = {}
    for room in kb.rooms.values():
        score = prior.get(room.name, 1.0) if prior else 1.0
        score *= _tile_likelihood(room, obs)
        score *= _prefab_likelihood(kb, room, obs)
        if room.name in obs.room_hints:
            score *= 50.0
        if obs.background_like is True and room.name.startswith("BG"):
            score *= 4.0
        if obs.background_like is False and room.name.startswith("BG"):
            score *= 0.3
        scores[room.name] = score
    return normalize(scores)


def score_tasks_from_rooms(kb: KnowledgeBase, room_probs: dict[str, float], prior: dict[str, float] | None = None) -> dict[str, float]:
    scores: dict[str, float] = {}
    for task in kb.tasks.values():
        score = prior.get(task.name, 1.0) if prior else 1.0
        task_room_mass = 0.0
        total_count = sum(task.room_choices.values()) or 1.0
        for room, count in task.room_choices.items():
            task_room_mass += room_probs.get(room, 0.0) * (count / total_count)
        score *= 0.2 + 12.0 * task_room_mass
        scores[task.name] = score
    return normalize(scores)


def _task_feature_likelihood(kb: KnowledgeBase, task: TaskDef, obs: Observation) -> float:
    prefab_counts = _prefab_counts(obs)
    if not prefab_counts:
        return 1.0

    score = 1.0
    blacklist_penalty = 0.04
    for prefab, count in prefab_counts.items():
        chains = kb.target_chains.get(prefab, ())
        task_level_chains = [
            chain
            for chain in chains
            if chain.static_layout and not chain.room and _count_matches_chain(chain, count)
        ]
        if not task_level_chains:
            continue

        if not any(chain.task == task.name for chain in task_level_chains):
            score *= blacklist_penalty ** min(count, 2)
    return score


def _apply_task_feature_likelihood(kb: KnowledgeBase, task_probs: dict[str, float], obs: Observation) -> dict[str, float]:
    feature_scores = {
        task.name: task_probs.get(task.name, 0.0) * _task_feature_likelihood(kb, task, obs)
        for task in kb.tasks.values()
    }
    return normalize(feature_scores)


def score_tasks(kb: KnowledgeBase, obs: Observation, prior: dict[str, float] | None = None) -> tuple[dict[str, float], dict[str, float]]:
    room_probs = score_rooms(kb, obs)
    task_probs = score_tasks_from_rooms(kb, room_probs, prior)
    task_probs = _apply_task_feature_likelihood(kb, task_probs, obs)
    for hint in obs.task_hints:
        if hint in task_probs:
            boosted = dict(task_probs)
            boosted[hint] *= 20.0
            task_probs = normalize(boosted)
    return task_probs, room_probs


def update_belief(kb: KnowledgeBase, belief: BeliefState, obs: Observation) -> BeliefState:
    room_probs = score_rooms(kb, obs, dict(belief.room_probs))
    task_probs = score_tasks_from_rooms(kb, room_probs, dict(belief.task_probs))
    task_probs = _apply_task_feature_likelihood(kb, task_probs, obs)
    if obs.task_hints:
        boosted = dict(task_probs)
        for hint in obs.task_hints:
            if hint in boosted:
                boosted[hint] *= 20.0
        task_probs = normalize(boosted)
    keys = infer_known_keys(kb, dict(task_probs)) | set(belief.known_keys)
    return BeliefState(task_probs=task_probs, room_probs=room_probs, known_keys=frozenset(keys))


def task_unlock_probability(kb: KnowledgeBase, task: TaskDef, known_keys: frozenset[str]) -> float:
    if not task.locks or task.locks == ("NONE",):
        return 1.0
    probability = 1.0
    for lock in task.locks:
        allowed = kb.lock_to_keys.get(lock, ())
        probability *= 1.0 if any(key in known_keys for key in allowed) else 0.15
    return probability


def entropy(probs: dict[str, float]) -> float:
    return -sum(p * math.log2(p) for p in probs.values() if p > 0)


def top_items(probs: dict[str, float], limit: int = 5) -> list[tuple[str, float]]:
    return sorted(probs.items(), key=lambda item: item[1], reverse=True)[:limit]


def aggregate_room_to_tasks(kb: KnowledgeBase, room_probs: dict[str, float]) -> dict[str, float]:
    agg: defaultdict[str, float] = defaultdict(float)
    for task in kb.tasks.values():
        total_count = sum(task.room_choices.values()) or 1.0
        for room, count in task.room_choices.items():
            agg[task.name] += room_probs.get(room, 0.0) * count / total_count
    return normalize(dict(agg))
