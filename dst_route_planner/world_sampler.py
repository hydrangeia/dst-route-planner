"""Sample taskset membership and approximate task-level worldgen topology.

Task connections approximate DST's default forest ``LinkNodesByKeys`` logic.
They describe generation parent relationships, not gameplay unlock requirements,
room coordinates, or physical map geometry. The model omits node-level rooms,
cross-links, and the later start-to-end loop insertion.
"""

from __future__ import annotations

import random
from collections import deque
from collections import defaultdict
from collections.abc import Collection
from typing import Protocol

from dst_route_planner.models import KnowledgeBase, SampledTaskGraph, TaskDef, TaskGraphEdge


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


def _ordered_unique(names: Collection[str]) -> list[str]:
    return list(dict.fromkeys(names))


def _matching_parent_keys(
    task: TaskDef,
    key_providers: dict[str, list[str]],
    lock_to_keys: dict[str, tuple[str, ...]],
    fallback_parent: str,
) -> dict[str, set[str]] | None:
    """Return prior task parents supplying keys that match the task's locks.

    DST's default forest linker tests every lock against accumulated keys, then
    chooses a parent from the union of task nodes that supplied a matching key.
    A selected parent therefore need not satisfy every lock by itself.
    """
    if not task.locks:
        return {fallback_parent: set()}

    matching_by_parent: dict[str, set[str]] = {}
    for lock in task.locks:
        # In DST's lockandkey.lua, LOCKS.NONE maps to an empty key list. It is
        # accepted as a starting task by _FindStartingTask, but a later task
        # carrying that lock cannot be unlocked through accumulated keys.
        if lock == "NONE":
            return None
        matching_keys = [
            key for key in lock_to_keys.get(lock, ()) if key in key_providers
        ]
        if not matching_keys:
            return None
        for key in matching_keys:
            for provider in key_providers[key]:
                matching_by_parent.setdefault(provider, set()).add(key)
    return matching_by_parent


def build_random_task_graph(
    kb: KnowledgeBase,
    num_optional_tasks: int = DEFAULT_NUM_OPTIONAL_TASKS,
    *,
    seed: int | None = None,
    rng: _RandomSource | None = None,
) -> SampledTaskGraph:
    """Sample taskset members and add task-level parent connections.

    The default forest path uses ``LinkNodesByKeys``: keys accumulate from all
    already connected tasks, a task is normally added when every lock has a
    matching key, and its parent is chosen from prior tasks that supplied any
    matching key. When no remaining task can unlock, storygen force-connects a
    random remaining task to the last task. Task order choice is sampled among
    currently eligible tasks because Lua ``pairs`` order is not portable; the
    source's default parent choice is random among matching key providers.
    This records task-level topology, not rooms or coordinates.
    """
    if seed is not None and rng is not None:
        raise ValueError("pass either seed or rng, not both")
    chooser = rng or (random.Random(seed) if seed is not None else random)

    required = [name for name, task in kb.tasks.items() if task.required]
    selected_optional = _select_optional_tasks(kb, num_optional_tasks, chooser)
    task_names = tuple(_ordered_unique([*required, *kb.start_tasks, *selected_optional]))
    if not task_names:
        return SampledTaskGraph((), tuple(), tuple(), None, tuple())

    initial_tasks = [
        name
        for name in task_names
        if not kb.tasks[name].locks or kb.tasks[name].locks[0] == "NONE"
    ]
    start_task = chooser.choice(initial_tasks or list(task_names))
    order = [start_task]
    remaining = [name for name in task_names if name != start_task]
    edges: list[TaskGraphEdge] = []
    key_providers: dict[str, list[str]] = defaultdict(list)
    for key in kb.tasks[start_task].keys_given:
        key_providers[key].append(start_task)

    while remaining:
        parent_options: dict[str, dict[str, set[str]]] = {}
        for task_name in remaining:
            matching = _matching_parent_keys(
                kb.tasks[task_name], key_providers, kb.lock_to_keys, order[-1]
            )
            if matching is not None:
                parent_options[task_name] = matching

        if parent_options:
            # Lua pairs iteration does not provide a portable stable task order;
            # seeded uniform choice approximates its first-unlockable selection.
            task_name = chooser.choice(list(parent_options))
            matching = parent_options[task_name]
            parent_names = [name for name in order if name in matching]
            parent_task = chooser.choice(parent_names)
            edge = TaskGraphEdge(
                parent_task=parent_task,
                child_task=task_name,
                forced=False,
                matched_keys=tuple(sorted(matching[parent_task])),
            )
        else:
            # Storygen falls back to connecting one random unused task to the
            # most recently added task when no lock-valid candidate remains.
            task_name = chooser.choice(remaining)
            edge = TaskGraphEdge(
                parent_task=order[-1],
                child_task=task_name,
                forced=True,
            )

        edges.append(edge)
        order.append(task_name)
        remaining.remove(task_name)
        for key in kb.tasks[task_name].keys_given:
            key_providers[key].append(task_name)

    return SampledTaskGraph(
        tasks=task_names,
        selected_optional_tasks=tuple(selected_optional),
        edges=tuple(edges),
        start_task=start_task,
        order=tuple(order),
    )


def task_graph_shortest_hops(graph: SampledTaskGraph, target_task: str) -> dict[str, int]:
    """Return undirected shortest-hop distances from a task in the graph."""
    if target_task not in graph.tasks:
        return {}

    neighbors = {task: set() for task in graph.tasks}
    for edge in graph.edges:
        if edge.parent_task in neighbors and edge.child_task in neighbors:
            neighbors[edge.parent_task].add(edge.child_task)
            neighbors[edge.child_task].add(edge.parent_task)

    distances = {target_task: 0}
    queue = deque([target_task])
    while queue:
        task_name = queue.popleft()
        for neighbor in neighbors[task_name]:
            if neighbor not in distances:
                distances[neighbor] = distances[task_name] + 1
                queue.append(neighbor)
    return distances


def task_graph_closeness(graph: SampledTaskGraph, target_task: str) -> dict[str, float]:
    """Map shortest task-connection hops to inverse-hop closeness scores."""
    return {
        task: 1.0 / (1.0 + hops)
        for task, hops in task_graph_shortest_hops(graph, target_task).items()
    }


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
    """Estimate inverse shortest-hop closeness to a task across sampled graphs.

    Graph edges are traversable in either direction. Scores are averaged over
    samples whose selected taskset contains the target; absent optional tasks
    contribute no score in a sample. These are task-connection hops, not map
    distance or physical-room topology.
    """
    if target_task not in kb.tasks or num_samples <= 0:
        return {}

    distance_scores: defaultdict[str, float] = defaultdict(float)
    graphs_with_target = 0
    rng = random.Random(seed) if seed is not None else random

    for _ in range(num_samples):
        graph = build_random_task_graph(kb, num_optional_tasks, rng=rng)
        if target_task not in graph.tasks:
            continue

        graphs_with_target += 1
        for task, closeness in task_graph_closeness(graph, target_task).items():
            distance_scores[task] += closeness

    if graphs_with_target <= 0:
        return {}

    return {task: score / graphs_with_target for task, score in distance_scores.items()}
