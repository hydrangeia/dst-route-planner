"""Regression checks for taskset sampling and lock-valid unlock sequences."""

from __future__ import annotations

from dataclasses import replace

import pytest

from dst_route_planner.knowledge import build_forest_default_kb
from dst_route_planner.world_sampler import (
    DEFAULT_NUM_OPTIONAL_TASKS,
    build_random_valid_chain,
    can_unlock,
    sample_task_distances,
    sample_task_graph,
    select_optional_tasks,
)


def test_optional_selection_is_exact_without_replacement() -> None:
    kb = build_forest_default_kb()
    optional_names = {name for name, task in kb.tasks.items() if not task.required}

    selected = select_optional_tasks(kb, seed=41)
    assert len(selected) == DEFAULT_NUM_OPTIONAL_TASKS == 5
    assert len(selected) == len(set(selected))
    assert set(selected) <= optional_names

    assert len(select_optional_tasks(kb, 100, seed=41)) == len(optional_names)
    assert len(select_optional_tasks(kb, 0, seed=41)) == 0
    with pytest.raises(ValueError, match="non-negative"):
        select_optional_tasks(kb, -1, seed=41)


def test_unlock_sequence_is_unique_lock_valid_and_retains_required_tasks() -> None:
    kb = build_forest_default_kb()
    required = {name for name, task in kb.tasks.items() if task.required}
    optional = {name for name, task in kb.tasks.items() if not task.required}

    for seed in range(30):
        chain = build_random_valid_chain(kb, seed=seed)
        assert len(chain) == len(set(chain))
        assert required <= set(chain)
        assert len(set(chain) & optional) <= DEFAULT_NUM_OPTIONAL_TASKS

        known_keys = {"NONE"}
        for task_name in chain:
            if task_name not in kb.start_tasks:
                assert can_unlock(kb.tasks[task_name], known_keys, kb.lock_to_keys)
            known_keys.update(kb.tasks[task_name].keys_given)


def test_optional_membership_is_distinct_from_unlock_reachability() -> None:
    kb = build_forest_default_kb()
    # Seed 1 selects Killer bees! but not its optional BEEHAT key producer.
    selected = select_optional_tasks(kb, seed=1)
    chain = build_random_valid_chain(kb, seed=1)
    task_probs = sample_task_graph(kb, num_samples=1, seed=1)

    assert "Killer bees!" in selected
    assert "Make a Beehat" not in selected
    assert "Killer bees!" not in chain
    assert task_probs["Killer bees!"] == 1.0


def test_taskset_probabilities_do_not_require_a_complete_unlock_sequence() -> None:
    kb = build_forest_default_kb()
    tasks = dict(kb.tasks)
    tasks["Great Plains"] = replace(tasks["Great Plains"], locks=("UNKNOWN_LOCK",))
    incomplete_kb = replace(kb, tasks=tasks)

    with pytest.raises(ValueError, match="required tasks remain locked"):
        build_random_valid_chain(incomplete_kb, seed=23)

    probabilities = sample_task_graph(incomplete_kb, num_samples=1, seed=1)
    assert probabilities["Great Plains"] == 1.0
    assert probabilities["Killer bees!"] == 1.0


def test_sampling_is_reproducible_and_presence_probabilities_are_balanced() -> None:
    kb = build_forest_default_kb()
    required = {name for name, task in kb.tasks.items() if task.required}
    optional = {name for name, task in kb.tasks.items() if not task.required}

    assert build_random_valid_chain(kb, seed=9) == build_random_valid_chain(kb, seed=9)
    assert sample_task_graph(kb, 200, seed=17) == sample_task_graph(kb, 200, seed=17)
    assert sample_task_distances(kb, "Speak to the king", 100, seed=17) == sample_task_distances(
        kb, "Speak to the king", 100, seed=17
    )

    probabilities = sample_task_graph(kb, num_samples=1000, seed=2026)
    assert all(probabilities[name] == 1.0 for name in required)
    assert sum(probabilities[name] for name in optional) == pytest.approx(5.0, abs=0.03)
    assert all(0.43 <= probabilities[name] <= 0.57 for name in optional)


def test_sampling_handles_empty_samples_and_unknown_targets() -> None:
    kb = build_forest_default_kb()

    assert sample_task_graph(kb, num_samples=0, seed=1) == {}
    assert sample_task_graph(kb, num_samples=-1, seed=1) == {}
    assert sample_task_distances(kb, "missing task", seed=1) == {}
    assert sample_task_distances(kb, "Speak to the king", num_samples=0, seed=1) == {}
