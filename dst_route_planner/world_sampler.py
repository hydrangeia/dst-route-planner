"""Sample taskset membership and lock-valid task-unlock sequences.

This is a simplified task-order model, not a spatial world-generation graph.
Taskset membership follows required tasks plus a sampled optional-task subset;
unlock sequences follow the KB's lock/key rules.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Collection
from typing import Protocol

from dst_route_planner.models import KnowledgeBase, TaskDef


DEFAULT_NUM_OPTIONAL_TASKS = 5


class _RandomSource(Protocol):
    def choice(self, seq): ...

    def choices(self, population, weights=None, *, cum_weights=None, k=1): ...


def can_unlock(task: TaskDef, known_keys: set[str], lock_to_keys: dict[str, tuple[str, ...]]) -> bool:
    """Check if a task can be unlocked given the known keys."""
    if not task.locks or task.locks == ("NONE",):
        return True
    for lock in task.locks:
        allowed_keys = lock_to_keys.get(lock, ())
        if not any(key in known_keys for key in allowed_keys):
            return False
    return True


def available_tasks(
    kb: KnowledgeBase,
    completed: set[str],
    known_keys: set[str],
    eligible_tasks: Collection[str] | None = None,
) -> list[str]:
    """Find all tasks that can be unlocked given current state."""
    available = []
    for task_name, task in kb.tasks.items():
        if (
            (eligible_tasks is None or task_name in eligible_tasks)
            and task_name not in completed
            and can_unlock(task, known_keys, kb.lock_to_keys)
        ):
            available.append(task_name)
    return available


def _select_optional_tasks(
    kb: KnowledgeBase,
    num_optional_tasks: int,
    rng: _RandomSource,
) -> list[str]:
    """Select optional tasks without replacement, weighted by optional_weight."""
    if num_optional_tasks < 0:
        raise ValueError("num_optional_tasks must be non-negative")

    remaining = [name for name, task in kb.tasks.items() if not task.required]
    selected: list[str] = []
    for _ in range(min(num_optional_tasks, len(remaining))):
        weights = [max(0.0, float(kb.tasks[name].optional_weight)) for name in remaining]
        if sum(weights) <= 0:
            choice = rng.choice(remaining)
        else:
            # When only some weights are positive, zero-weight candidates are
            # kept as a fallback after the positive-weight candidates are used.
            choice = rng.choices(remaining, weights=weights, k=1)[0]
        selected.append(choice)
        remaining.remove(choice)
    return selected


def select_optional_tasks(
    kb: KnowledgeBase,
    num_optional_tasks: int = DEFAULT_NUM_OPTIONAL_TASKS,
    *,
    seed: int | None = None,
    rng: _RandomSource | None = None,
) -> list[str]:
    """Return the taskset's optional-task selection, without lock filtering."""
    if seed is not None and rng is not None:
        raise ValueError("pass either seed or rng, not both")
    chooser = rng or (random.Random(seed) if seed is not None else random)
    return _select_optional_tasks(kb, num_optional_tasks, chooser)


def build_random_valid_chain(
    kb: KnowledgeBase,
    num_optional_tasks: int = DEFAULT_NUM_OPTIONAL_TASKS,
    *,
    seed: int | None = None,
    rng: _RandomSource | None = None,
) -> list[str]:
    """Build a strict lock-valid sequence from required and sampled optional tasks.

    Required tasks remain eligible in every sample. Optional tasks are first
    selected without replacement, then added to the returned sequence only
    when their lock prerequisites are satisfied. An optional task can be in
    the selected taskset but absent from this sequence if its key is missing.
    This strict sequence does not model storygen.lua's fallback random edge.
    Pass ``seed`` (or a random source via ``rng``) for reproducibility.
    """
    if seed is not None and rng is not None:
        raise ValueError("pass either seed or rng, not both")
    chooser = rng or (random.Random(seed) if seed is not None else random)

    chain, _ = _build_chain_and_task_set(kb, num_optional_tasks, chooser)
    return chain


def _build_chain_and_task_set(
    kb: KnowledgeBase,
    num_optional_tasks: int,
    chooser: _RandomSource,
) -> tuple[list[str], set[str]]:
    required = {name for name, task in kb.tasks.items() if task.required}
    selected_optional = _select_optional_tasks(kb, num_optional_tasks, chooser)
    eligible = required | set(selected_optional) | set(kb.start_tasks)

    chain = list(kb.start_tasks)
    completed = set(chain)
    known_keys = {"NONE"}

    # Add keys from start tasks
    for task_name in chain:
        known_keys.update(kb.tasks[task_name].keys_given)

    # Greedily add more tasks until no more can be unlocked
    # Use random selection when multiple tasks are available
    while True:
        available = available_tasks(kb, completed, known_keys, eligible)
        if not available:
            break

        task_name = chooser.choice(available)
        chain.append(task_name)
        completed.add(task_name)
        known_keys.update(kb.tasks[task_name].keys_given)

    missing_required = required - completed
    if missing_required:
        names = ", ".join(sorted(missing_required))
        raise ValueError(
            "could not build a lock-valid chain containing all required tasks; "
            f"required tasks remain locked: {names}"
        )

    return chain, eligible


def sample_task_graph(
    kb: KnowledgeBase,
    num_samples: int = 1000,
    num_optional_tasks: int = DEFAULT_NUM_OPTIONAL_TASKS,
    *,
    seed: int | None = None,
) -> dict[str, float]:
    """Sample tasksets and return empirical task presence probabilities.

    Args:
        kb: Knowledge base with task definitions and optional weights
        num_samples: Number of tasksets to sample
        num_optional_tasks: Number of optional candidates selected per taskset
        seed: Optional seed for reproducible sampling

    Returns:
        Dictionary mapping task names to appearance probability in sampled
        tasksets. Required tasks and start tasks are always included; each
        optional taskset contains up to ``num_optional_tasks`` selected tasks.
    """
    if num_samples <= 0:
        return {}

    task_counts: defaultdict[str, int] = defaultdict(int)
    rng = random.Random(seed) if seed is not None else random
    required = {name for name, task in kb.tasks.items() if task.required}
    always_present = required | set(kb.start_tasks)

    for _ in range(num_samples):
        task_set = always_present | set(_select_optional_tasks(kb, num_optional_tasks, rng))
        for task in task_set:
            task_counts[task] += 1

    return {task: count / num_samples for task, count in task_counts.items()}


def sample_task_distances(
    kb: KnowledgeBase,
    target_task: str,
    num_samples: int = 1000,
    num_optional_tasks: int = DEFAULT_NUM_OPTIONAL_TASKS,
    *,
    seed: int | None = None,
) -> dict[str, float]:
    """Estimate sequence closeness to a target from strict unlock sequences.

    The scores are inverse-order-distance averages for samples whose strict
    lock-valid sequence contains the target. They approximate sequence
    proximity only; they are neither map distance nor a spatial topology.
    """
    if target_task not in kb.tasks or num_samples <= 0:
        return {}

    distance_scores: defaultdict[str, float] = defaultdict(float)
    chains_with_target = 0
    rng = random.Random(seed) if seed is not None else random

    for _ in range(num_samples):
        chain, _ = _build_chain_and_task_set(kb, num_optional_tasks, rng)

        if target_task not in chain:
            continue

        chains_with_target += 1
        target_idx = chain.index(target_task)

        for i, task in enumerate(chain):
            if task == target_task:
                distance_scores[task] += 1.0
            else:
                distance = abs(i - target_idx)
                closeness = 1.0 / (1.0 + distance)
                distance_scores[task] += closeness

    if chains_with_target <= 0:
        return {}

    return {task: score / chains_with_target for task, score in distance_scores.items()}
