"""Regression checks for task-level connection graphs and graph-hop scores."""

from __future__ import annotations

import pytest

from dst_route_planner.inference import initial_belief
from dst_route_planner.knowledge import build_forest_default_kb
from dst_route_planner.models import (
    Direction,
    DirectionObservation,
    KnowledgeBase,
    Observation,
    SampledTaskGraph,
    TaskDef,
    TaskGraphEdge,
)
from dst_route_planner.navigation import _get_task_distances, rank_directions
from dst_route_planner.world_sampler import (
    DEFAULT_NUM_OPTIONAL_TASKS,
    build_random_task_graph,
    sample_task_distances,
    task_graph_closeness,
    task_graph_shortest_hops,
)


def test_default_graph_has_required_tasks_five_optionals_and_connected_edges() -> None:
    kb = build_forest_default_kb()
    required = {name for name, task in kb.tasks.items() if task.required}
    optional = {name for name, task in kb.tasks.items() if not task.required}

    for seed in range(20):
        graph = build_random_task_graph(kb, seed=seed)
        assert len(graph.tasks) == 15
        assert len(graph.tasks) == len(set(graph.tasks))
        assert required <= set(graph.tasks)
        assert len(graph.selected_optional_tasks) == DEFAULT_NUM_OPTIONAL_TASKS
        assert len(graph.selected_optional_tasks) == len(set(graph.selected_optional_tasks))
        assert set(graph.selected_optional_tasks) <= optional
        assert set(graph.tasks) == required | set(graph.selected_optional_tasks)
        assert graph.start_task == graph.order[0]
        assert set(graph.order) == set(graph.tasks)
        assert len(graph.order) == len(set(graph.order))
        assert len(graph.edges) == len(graph.tasks) - 1
        assert [edge.child_task for edge in graph.edges] == list(graph.order[1:])
        assert all(edge.parent_task in graph.tasks for edge in graph.edges)
        assert all(edge.child_task in graph.tasks for edge in graph.edges)
        assert all(edge.parent_task != edge.child_task for edge in graph.edges)
        assert set(task_graph_shortest_hops(graph, graph.start_task)) == set(graph.tasks)


def test_normal_edges_use_accumulated_lock_keys_and_parent_key_matches() -> None:
    kb = build_forest_default_kb()
    graph = build_random_task_graph(kb, seed=0)
    known_keys = set(kb.tasks[graph.start_task].keys_given)
    edges_by_child = {edge.child_task: edge for edge in graph.edges}

    assert not edges_by_child["Speak to the king"].forced
    assert not edges_by_child["Forest hunters"].forced

    for edge in graph.edges:
        task = kb.tasks[edge.child_task]
        if edge.forced:
            assert any(
                not any(key in known_keys for key in kb.lock_to_keys.get(lock, ()))
                for lock in task.locks
            )
            assert edge.parent_task == graph.order[graph.order.index(edge.child_task) - 1]
            assert edge.matched_keys == ()
        else:
            assert all(
                any(key in known_keys for key in kb.lock_to_keys.get(lock, ()))
                for lock in task.locks
            )
            if task.locks and task.locks != ("NONE",):
                parent_keys = set(kb.tasks[edge.parent_task].keys_given)
                allowed_keys = {
                    key
                    for lock in task.locks
                    for key in kb.lock_to_keys.get(lock, ())
                }
                assert set(edge.matched_keys) <= parent_keys & allowed_keys
                assert edge.matched_keys
        known_keys.update(task.keys_given)


def test_killer_bees_is_kept_and_force_connected_without_optional_beehat() -> None:
    kb = build_forest_default_kb()
    graph = build_random_task_graph(kb, seed=1)
    edges = {edge.child_task: edge for edge in graph.edges}

    assert "Killer bees!" in graph.tasks
    assert "Killer bees!" in graph.selected_optional_tasks
    assert "Make a Beehat" not in graph.tasks
    assert edges["Killer bees!"].forced
    assert edges["Killer bees!"].parent_task == graph.order[-2]


def test_secondary_none_lock_uses_source_fallback_edge() -> None:
    tasks = {
        "start": TaskDef("start", ("NONE",), ("TIER1",), {}, "", "", required=True),
        "secondary start": TaskDef("secondary start", ("TIER1", "NONE"), (), {}, "", ""),
    }
    kb = KnowledgeBase(
        tasks=tasks,
        rooms={},
        static_layouts={},
        target_chains={},
        lock_to_keys={"NONE": ("NONE",), "TIER1": ("TIER1",)},
        start_tasks=("start",),
    )

    graph = build_random_task_graph(kb, num_optional_tasks=1, seed=0)

    assert graph.start_task == "start"
    assert graph.tasks == ("start", "secondary start")
    assert graph.edges == (TaskGraphEdge("start", "secondary start", forced=True),)


def test_seed_repeats_graph_and_sampled_graph_distances() -> None:
    kb = build_forest_default_kb()
    assert build_random_task_graph(kb, seed=27) == build_random_task_graph(kb, seed=27)
    assert sample_task_distances(kb, "Speak to the king", 100, seed=27) == sample_task_distances(
        kb, "Speak to the king", 100, seed=27
    )


def test_graph_closeness_uses_shortest_hops_instead_of_sequence_indices(monkeypatch) -> None:
    kb = build_forest_default_kb()
    graph = SampledTaskGraph(
        tasks=("Make a pick", "Dig that rock", "Great Plains", "Squeltch"),
        selected_optional_tasks=(),
        edges=(
            TaskGraphEdge("Make a pick", "Squeltch"),
            TaskGraphEdge("Squeltch", "Great Plains"),
            TaskGraphEdge("Great Plains", "Dig that rock"),
        ),
        start_task="Make a pick",
        order=("Make a pick", "Dig that rock", "Great Plains", "Squeltch"),
    )
    expected = {
        "Make a pick": 1.0,
        "Squeltch": 0.5,
        "Great Plains": 1.0 / 3.0,
        "Dig that rock": 0.25,
    }

    assert task_graph_shortest_hops(graph, "Make a pick") == {
        "Make a pick": 0,
        "Squeltch": 1,
        "Great Plains": 2,
        "Dig that rock": 3,
    }
    assert task_graph_closeness(graph, "Make a pick") == expected

    monkeypatch.setattr("dst_route_planner.world_sampler.build_random_task_graph", lambda *args, **kwargs: graph)
    scores = sample_task_distances(kb, "Make a pick", num_samples=1, seed=4)
    assert scores == expected
    assert scores["Squeltch"] > scores["Dig that rock"]


def test_distance_sampling_empty_inputs() -> None:
    kb = build_forest_default_kb()
    assert sample_task_distances(kb, "missing task", seed=1) == {}
    assert sample_task_distances(kb, "Speak to the king", num_samples=0, seed=1) == {}
    optional = {name for name, task in kb.tasks.items() if not task.required}
    distances = sample_task_distances(
        kb, "Speak to the king", num_samples=10, num_optional_tasks=0, seed=1
    )
    assert distances
    assert not (set(distances) & optional)


def test_navigation_distance_cache_tracks_sampling_settings_and_kb(monkeypatch) -> None:
    import dst_route_planner.navigation as navigation

    old_owner = navigation._distance_cache_owner
    old_cache = dict(navigation._distance_cache)
    calls = []

    def fake_sample(kb, target_task, num_samples, num_optional_tasks, *, seed):
        calls.append((kb, target_task, num_samples, num_optional_tasks, seed))
        return {target_task: float(len(calls))}

    try:
        navigation._distance_cache_owner = None
        navigation._distance_cache.clear()
        monkeypatch.setattr(navigation, "sample_task_distances", fake_sample)
        kb = build_forest_default_kb()
        assert _get_task_distances(kb, "Make a pick", 7, seed=4)["Make a pick"] == 1.0
        assert _get_task_distances(kb, "Make a pick", 7, seed=4)["Make a pick"] == 1.0
        _get_task_distances(kb, "Make a pick", 8, seed=4)
        _get_task_distances(kb, "Make a pick", 7, seed=5)
        assert len(calls) == 3

        other_kb = build_forest_default_kb()
        _get_task_distances(other_kb, "Make a pick", 7, seed=4)
        assert len(calls) == 4
        assert navigation._distance_cache_owner is other_kb
        assert len(navigation._distance_cache) == 1
    finally:
        navigation._distance_cache.clear()
        navigation._distance_cache.update(old_cache)
        navigation._distance_cache_owner = old_owner


def test_rank_directions_forwards_the_reproducibility_seed(monkeypatch) -> None:
    import dst_route_planner.navigation as navigation

    seen_seeds = []

    def fake_distances(kb, target_task, num_samples=1000, num_optional_tasks=5, seed=0):
        seen_seeds.append(seed)
        return {}

    monkeypatch.setattr(navigation, "_get_task_distances", fake_distances)
    kb = build_forest_default_kb()
    observations = [DirectionObservation(Direction.NORTH, Observation())]
    rank_directions(kb, "panflute", initial_belief(kb), observations, seed=23)

    assert seen_seeds
    assert set(seen_seeds) == {23}
