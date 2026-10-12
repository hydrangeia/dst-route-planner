"""CLI checks for repeatable recommendations and inspectable task graphs."""

from __future__ import annotations

import json
import sys

from dst_route_planner.cli import main
from dst_route_planner.knowledge import build_forest_default_kb


def test_graph_json_keeps_selected_tasks_and_reports_forced_edges(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["route_planner.py", "--sample-graph", "--seed", "1"])
    assert main() == 0
    first = capsys.readouterr().out
    assert main() == 0
    assert capsys.readouterr().out == first

    graph = json.loads(first)
    kb = build_forest_default_kb()
    required = {name for name, task in kb.tasks.items() if task.required}
    assert graph["seed"] == 1
    assert len(graph["tasks"]) == len(set(graph["tasks"])) == 15
    assert len(graph["selected_optional_tasks"]) == 5
    assert required <= set(graph["tasks"])
    assert len(graph["edges"]) == 14
    assert {edge["child_task"] for edge in graph["edges"]} == set(graph["tasks"]) - {graph["start_task"]}
    assert "Killer bees!" in graph["selected_optional_tasks"]
    assert "Make a Beehat" not in graph["selected_optional_tasks"]
    assert any(edge["child_task"] == "Killer bees!" and edge["forced"] for edge in graph["edges"])


def test_cli_recommendations_are_repeatable_for_a_given_seed(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["route_planner.py", "--demo", "--seed", "23"])
    assert main() == 0
    first = capsys.readouterr().out
    assert main() == 0
    assert capsys.readouterr().out == first
    assert "Target: panflute" in first
    assert "Direction ranking:" in first
