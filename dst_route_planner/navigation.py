from __future__ import annotations

from dst_route_planner.inference import normalize, score_tasks, task_unlock_probability
from dst_route_planner.models import ActionScore, BeliefState, DirectionObservation, KnowledgeBase
from dst_route_planner.world_sampler import DEFAULT_NUM_OPTIONAL_TASKS, sample_task_distances


_distance_cache_owner: KnowledgeBase | None = None
_distance_cache: dict[tuple[str, int, int, int | None], dict[str, float]] = {}


def _get_task_distances(
    kb: KnowledgeBase,
    target_task: str,
    num_samples: int = 1000,
    num_optional_tasks: int = DEFAULT_NUM_OPTIONAL_TASKS,
    seed: int | None = 0,
) -> dict[str, float]:
    """Cache graph closeness samples by KB identity and sampling settings."""
    global _distance_cache_owner
    if _distance_cache_owner is not kb:
        _distance_cache.clear()
        _distance_cache_owner = kb

    cache_key = (target_task, num_samples, num_optional_tasks, seed)
    if cache_key not in _distance_cache:
        _distance_cache[cache_key] = sample_task_distances(
            kb,
            target_task,
            num_samples,
            num_optional_tasks,
            seed=seed,
        )
    return _distance_cache[cache_key]


def score_direction(
    kb: KnowledgeBase,
    target_prefab: str,
    belief: BeliefState,
    direction_obs: DirectionObservation,
    *,
    seed: int | None = 0,
) -> ActionScore:
    chains = kb.target_chains[target_prefab]
    task_probs, room_probs = score_tasks(kb, direction_obs.observation, dict(belief.task_probs))
    total_weight = sum(chain.weight for chain in chains) or 1.0
    target_task_probability = sum(task_probs.get(chain.task, 0.0) * chain.weight for chain in chains) / total_weight
    target_room_probability = sum(room_probs.get(chain.room, 0.0) * chain.weight for chain in chains if chain.room) / total_weight

    obs = direction_obs.observation
    connection_score = 1.0
    if obs.connection_like is True:
        connection_score *= 1.8
    elif obs.connection_like is False:
        connection_score *= 0.35
    if obs.background_like is True:
        connection_score *= 0.55
    elif obs.background_like is False:
        connection_score *= 1.15

    unlock_score = sum(
        task_unlock_probability(kb, kb.tasks[chain.task], belief.known_keys) * chain.weight
        for chain in chains
        if chain.task in kb.tasks
    ) / total_weight
    progress_score = 0.0
    for name, prob in task_probs.items():
        max_distance = 0.0
        for chain in chains:
            if chain.task in kb.tasks:
                distances = _get_task_distances(kb, chain.task, seed=seed)
                distance = distances.get(name, 0.0)
                max_distance = max(max_distance, distance)
        progress_score += prob * max_distance
    landmark_score = 0.0
    seen = direction_obs.observation.prefabs_seen
    target_visible = target_prefab in seen or direction_obs.observation.prefab_counts.get(target_prefab, 0) > 0
    landmark_prefabs = {prefab for chain in chains for prefab in chain.landmark_prefabs}
    for prefab in landmark_prefabs:
        if prefab in seen:
            landmark_score += 1.0
    if target_visible:
        landmark_score += 10.0

    evidence_score = (
        0.40 * target_task_probability
        + 0.30 * target_room_probability
        + 0.15 * progress_score
        + 0.10 * min(landmark_score, 2.0) / 2.0
        + 0.05 * unlock_score
    ) * connection_score
    score = evidence_score + (4.0 if target_visible else 0.0)

    explanation: list[str] = []
    if target_visible:
        explanation.append("target prefab visible; go directly there")
    if target_task_probability > 0.25:
        likely_tasks = sorted({chain.task for chain in chains}, key=lambda name: task_probs.get(name, 0.0), reverse=True)
        explanation.append(f"looks like target task {likely_tasks[0]}")
    if target_room_probability > 0.25:
        likely_rooms = sorted({chain.room for chain in chains if chain.room}, key=lambda name: room_probs.get(name, 0.0), reverse=True)
        if likely_rooms:
            explanation.append(f"looks like target room {likely_rooms[0]}")
    if landmark_score and not target_visible:
        explanation.append("target landmark prefab visible")
    if obs.connection_like is True:
        explanation.append("direction appears to cross into a connected room/task")
    if obs.background_like is True:
        explanation.append("background-like area, discounted")
    if not explanation:
        explanation.append("weak evidence; score mainly from task progression priors")

    return ActionScore(
        direction=direction_obs.direction,
        score=score,
        target_task_probability=target_task_probability,
        target_room_probability=target_room_probability,
        connection_score=connection_score,
        explanation=tuple(explanation),
    )


def rank_directions(
    kb: KnowledgeBase,
    target_prefab: str,
    belief: BeliefState,
    observations: list[DirectionObservation],
    *,
    seed: int | None = 0,
) -> list[ActionScore]:
    scores = [score_direction(kb, target_prefab, belief, obs, seed=seed) for obs in observations]
    return sorted(scores, key=lambda item: item.score, reverse=True)


def probabilities_by_direction(scores: list[ActionScore]) -> dict[str, float]:
    return normalize({score.direction.value: score.score for score in scores})
