from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from dst_route_planner import app
from dst_route_planner.exploration import CorruptExplorationError, ExplorationStore


def _snapshot(
    sequence: int,
    *,
    world_id: str = "world-abc",
    world_kind: str = "forest",
    session_id: str = "session-1",
) -> dict:
    demo = app._demo()
    return {
        "live_version": 1,
        "world_id": world_id,
        "world_kind": world_kind,
        "session_id": session_id,
        "sequence": sequence,
        "captured_at": time.time(),
        "position": {"x": float(sequence), "y": 0, "z": 0},
        "camera_heading": 270.0,
        "current": {"schema_version": 1, "tile_types": ["GRASS"]},
        "directions": copy.deepcopy(demo["directions"]),
        "landmarks": [{"prefab": "panflute", "x": 3, "z": 4}],
    }


def _capture(store: ExplorationStore, sequence: int, **identity) -> dict:
    return store.capture(
        _snapshot(sequence, **identity),
        target="panflute",
        seed=13,
        plan={"target": "panflute", "seed": 13},
    )


def test_exploration_id_is_opaque_and_sessions_deduplicate_after_restart(tmp_path) -> None:
    store = ExplorationStore(tmp_path)
    snapshot = _snapshot(1)
    first = store.capture(snapshot, target="panflute", seed=13, plan={"target": "panflute"})
    journal_path = tmp_path / f"{first['id']}.jsonl"
    original = journal_path.read_bytes()

    assert re.fullmatch(r"[0-9a-f]{64}", first["id"])
    lines = [json.loads(line) for line in original.splitlines()]
    assert lines[0] == {
        "replay_version": 1,
        "id": first["id"],
        "world_id": "world-abc",
        "world_kind": "forest",
        "session_id": "session-1",
    }
    assert lines[1]["snapshot"] == snapshot
    assert lines[1]["target"] == "panflute"
    assert lines[1]["seed"] == 13
    assert lines[1]["plan"] == {"target": "panflute"}

    restarted_store = ExplorationStore(tmp_path)
    duplicate = _capture(restarted_store, 1)

    assert duplicate["frame_count"] == 1
    assert duplicate["status"] == "recording"
    assert journal_path.read_bytes() == original

    second = _capture(restarted_store, 2)
    assert second["frame_count"] == 2
    older = _capture(ExplorationStore(tmp_path), 1)
    assert older["frame_count"] == 2
    assert len(journal_path.read_bytes().splitlines()) == 3


def test_partial_final_line_is_truncated_before_next_append(tmp_path, monkeypatch) -> None:
    store = ExplorationStore(tmp_path)
    first = _capture(store, 1)
    path = tmp_path / f"{first['id']}.jsonl"
    complete_before_partial = path.read_bytes()
    path.write_bytes(complete_before_partial + b'{"replay_version":1,"snapshot":')
    parse_count = 0
    original_reader = store._read_journal_bytes

    def count_parse(*args, **kwargs):
        nonlocal parse_count
        parse_count += 1
        return original_reader(*args, **kwargs)

    monkeypatch.setattr(store, "_read_journal_bytes", count_parse)

    result = _capture(store, 2)

    lines = [json.loads(line) for line in path.read_bytes().splitlines()]
    assert result["frame_count"] == 2
    assert len(lines) == 3
    assert lines[0]["id"] == first["id"]
    assert [line["snapshot"]["sequence"] for line in lines[1:]] == [1, 2]
    assert parse_count == 1


def test_cached_journal_metadata_serves_repeat_capture_summary_and_list(tmp_path, monkeypatch) -> None:
    store = ExplorationStore(tmp_path)
    first = _capture(store, 1)
    parse_count = 0
    original_reader = store._read_journal_bytes

    def count_parse(*args, **kwargs):
        nonlocal parse_count
        parse_count += 1
        return original_reader(*args, **kwargs)

    monkeypatch.setattr(store, "_read_journal_bytes", count_parse)

    assert _capture(store, 1)["frame_count"] == 1
    assert store.summary_for_snapshot(_snapshot(2))["frame_count"] == 1
    assert store.list_explorations()[0]["frame_count"] == 1
    assert _capture(store, 2)["frame_count"] == 2
    assert store.list_explorations()[0]["frame_count"] == 2
    assert parse_count == 0


def test_corrupt_complete_journal_is_preserved_and_rejected(tmp_path) -> None:
    store = ExplorationStore(tmp_path)
    first = _capture(store, 1)
    path = tmp_path / f"{first['id']}.jsonl"
    path.write_bytes(path.read_bytes() + b"not-json\n")
    corrupt_bytes = path.read_bytes()

    with pytest.raises(CorruptExplorationError):
        _capture(ExplorationStore(tmp_path), 2)

    assert path.read_bytes() == corrupt_bytes


def test_world_kind_and_session_changes_create_separate_journals(tmp_path) -> None:
    store = ExplorationStore(tmp_path)
    forest = _capture(store, 1)
    other_session = _capture(store, 1, session_id="session-2")
    cave = _capture(store, 1, world_kind="cave")
    other_world = _capture(store, 1, world_id="world-def")

    assert len({forest["id"], other_session["id"], cave["id"], other_world["id"]}) == 4
    assert {item["id"] for item in store.list_explorations()} == {
        forest["id"],
        other_session["id"],
        cave["id"],
        other_world["id"],
    }


def test_concurrent_duplicate_captures_append_only_once(tmp_path) -> None:
    store = ExplorationStore(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: _capture(store, 1), range(16)))

    assert all(result["frame_count"] == 1 for result in results)
    journal_path = tmp_path / f"{results[0]['id']}.jsonl"
    assert len(journal_path.read_bytes().splitlines()) == 2


def test_separate_processes_share_journal_lock_and_deduplicate(tmp_path) -> None:
    script = r'''
import json, sys, time
from dst_route_planner import app
from dst_route_planner.exploration import ExplorationStore

snapshot = {
    "live_version": 1,
    "world_id": "process-world",
    "world_kind": "forest",
    "session_id": "process-session",
    "sequence": 1,
    "captured_at": time.time(),
    "position": {"x": 0, "y": 0, "z": 0},
    "camera_heading": 0,
    "current": {"schema_version": 1, "tile_types": ["GRASS"]},
    "directions": app._demo()["directions"],
}
result = ExplorationStore(sys.argv[1]).capture(snapshot, target="panflute", seed=0)
print(json.dumps(result))
'''
    project_dir = str(Path(__file__).resolve().parent)
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path)],
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    outputs = [process.communicate(timeout=30) for process in processes]

    assert all(process.returncode == 0 for process in processes), outputs
    summaries = [json.loads(stdout) for stdout, _ in outputs]
    assert [summary["frame_count"] for summary in summaries] == [1, 1]
    assert summaries[0]["id"] == summaries[1]["id"]
    journal_path = tmp_path / f"{summaries[0]['id']}.jsonl"
    lines = [json.loads(line) for line in journal_path.read_bytes().splitlines()]
    assert len(lines) == 2
    assert [line.get("snapshot", {}).get("sequence") for line in lines[1:]] == [1]


def test_frame_and_byte_limits_preserve_the_existing_download(tmp_path, monkeypatch) -> None:
    import dst_route_planner.exploration as exploration

    store = ExplorationStore(tmp_path)
    monkeypatch.setattr(exploration, "MAX_EXPLORATION_FRAMES", 2)
    first = _capture(store, 1)
    second = _capture(store, 2)
    path = tmp_path / f"{first['id']}.jsonl"
    at_frame_limit = path.read_bytes()

    assert second["status"] == "limit_reached"
    third = _capture(store, 3)
    assert third["status"] == "limit_reached"
    assert third["frame_count"] == 2
    assert path.read_bytes() == at_frame_limit

    monkeypatch.setattr(exploration, "MAX_EXPLORATION_FRAMES", 10_000)
    monkeypatch.setattr(exploration, "MAX_EXPLORATION_BYTES", len(at_frame_limit))
    fourth = _capture(store, 4)
    assert fourth["status"] == "limit_reached"
    assert fourth["frame_count"] == 2
    assert path.read_bytes() == at_frame_limit
