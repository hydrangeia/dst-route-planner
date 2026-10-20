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
from dst_route_planner.exploration import (
    CorruptExplorationError,
    ExplorationConflictError,
    ExplorationStore,
    ExplorationTooLargeError,
    exploration_id,
)


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


def _import_replay(*sequences: int, world_id: str = "import-world", session_id: str = "import-session") -> bytes:
    world_kind = "forest"
    journal_id = exploration_id(world_id, world_kind, session_id)
    header = {
        "replay_version": 1,
        "id": journal_id,
        "world_id": world_id,
        "world_kind": world_kind,
        "session_id": session_id,
    }
    rows = [header]
    for sequence in sequences:
        rows.append(
            {
                "replay_version": 1,
                "received_at": f"2026-02-01T00:00:{sequence:02d}Z",
                "target": "panflute",
                "seed": 7,
                "snapshot": _snapshot(
                    sequence, world_id=world_id, world_kind=world_kind, session_id=session_id
                ),
            }
        )
    return b"\n".join(json.dumps(row, separators=(",", ":")).encode("utf-8") for row in rows)


def test_import_roundtrips_old_replays_and_allows_capture_to_continue(tmp_path) -> None:
    store = ExplorationStore(tmp_path)
    raw = _import_replay(1, 2)

    summary, created = store.import_bytes(raw)

    assert created is True
    assert summary["frame_count"] == 2
    assert summary["status"] == "recording"
    imported = raw + b"\n"
    assert store.get_bytes(summary["id"]) == imported
    assert store.list_explorations() == [summary]
    frames = [json.loads(line) for line in imported.splitlines()][1:]
    assert all("terrain" not in frame["snapshot"] for frame in frames)
    assert all("player_anchor" not in frame["snapshot"] for frame in frames)

    continued = store.capture(
        _snapshot(3, world_id="import-world", session_id="import-session"),
        target="panflute",
        seed=7,
    )
    assert continued["frame_count"] == 3
    assert [
        json.loads(line).get("snapshot", {}).get("sequence")
        for line in store.get_bytes(summary["id"]).splitlines()[1:]
    ] == [1, 2, 3]


def test_import_is_semantically_idempotent_and_conflicts_never_replace(tmp_path) -> None:
    store = ExplorationStore(tmp_path)
    raw = _import_replay(1)
    first, created = store.import_bytes(raw)
    path = tmp_path / f"{first['id']}.jsonl"
    original = path.read_bytes()

    rows = [json.loads(line) for line in (raw + b"\n").splitlines()]
    reformatted = b"\n".join(
        json.dumps(row, ensure_ascii=True, sort_keys=True).encode("utf-8") for row in rows
    )
    duplicate, duplicate_created = store.import_bytes(reformatted)
    assert created is True
    assert duplicate_created is False
    assert duplicate == first
    assert path.read_bytes() == original

    changed = json.loads((raw + b"\n").splitlines()[1])
    changed["target"] = "pigking"
    conflicting = b"\n".join(
        [json.dumps(rows[0]).encode(), json.dumps(changed).encode()]
    )
    with pytest.raises(ExplorationConflictError):
        store.import_bytes(conflicting)
    assert path.read_bytes() == original


def test_import_rejects_invalid_journals_without_leaving_files(tmp_path) -> None:
    raw = _import_replay(1, 2)
    rows = [json.loads(line) for line in (raw + b"\n").splitlines()]
    wrong_identity = copy.deepcopy(rows)
    wrong_identity[0]["id"] = "0" * 64
    mixed_session = copy.deepcopy(rows)
    mixed_session[2]["snapshot"]["session_id"] = "other-session"
    decreasing = copy.deepcopy(rows)
    decreasing[2]["snapshot"]["sequence"] = 1
    unsupported = copy.deepcopy(rows)
    unsupported[1]["replay_version"] = 2

    cases = [
        raw + b"\nnot-json",
        b"\n".join(json.dumps(row).encode() for row in wrong_identity),
        b"\n".join(json.dumps(row).encode() for row in mixed_session),
        b"\n".join(json.dumps(row).encode() for row in decreasing),
        b"\n".join(json.dumps(row).encode() for row in unsupported),
        json.dumps(rows[0]).encode() + b"\n",
        b'{"replay_version":1,"replay_version":1}\n',
        b"\n".join(
            json.dumps(row).encode()
            for row in [{**rows[0], "replay_version": 2}, *rows[1:]]
        ),
    ]
    for invalid in cases:
        store = ExplorationStore(tmp_path / str(len(list(tmp_path.iterdir()))))
        with pytest.raises(CorruptExplorationError):
            store.import_bytes(invalid)
        assert not store.directory.exists()


def test_import_limits_frames_and_bytes_without_partial_files(tmp_path, monkeypatch) -> None:
    import dst_route_planner.exploration as exploration

    raw = _import_replay(1, 2)
    monkeypatch.setattr(exploration, "MAX_EXPLORATION_FRAMES", 1)
    store = ExplorationStore(tmp_path / "frames")
    with pytest.raises(ExplorationTooLargeError):
        store.import_bytes(raw)
    assert not store.directory.exists()

    monkeypatch.setattr(exploration, "MAX_EXPLORATION_FRAMES", 10_000)
    monkeypatch.setattr(exploration, "MAX_EXPLORATION_BYTES", len(raw))
    byte_store = ExplorationStore(tmp_path / "bytes")
    with pytest.raises(ExplorationTooLargeError):
        byte_store.import_bytes(raw)
    assert not byte_store.directory.exists()


def test_import_rejects_non_finite_numbers_and_duplicate_keys(tmp_path) -> None:
    raw = _import_replay(1)
    non_finite = raw.replace(b'"seed":7', b'"seed":7,"plan":{"score":1e999}')
    duplicate_key = raw.replace(b'"seed":7', b'"seed":7,"seed":7')
    for invalid in (non_finite, duplicate_key):
        with pytest.raises(CorruptExplorationError):
            ExplorationStore(tmp_path / str(len(list(tmp_path.iterdir())))).import_bytes(invalid)


def test_concurrent_imports_for_one_identity_publish_only_one_file(tmp_path) -> None:
    raw = _import_replay(1, 2)
    stores = [ExplorationStore(tmp_path) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(lambda store: store.import_bytes(raw), stores))

    assert sum(created for _, created in outcomes) == 1
    assert {summary["id"] for summary, _ in outcomes} == {
        exploration_id("import-world", "forest", "import-session")
    }
    assert len(list(tmp_path.glob("*.jsonl"))) == 1
    assert len(list(tmp_path.glob("*.tmp"))) == 0


def test_import_never_replaces_a_symlink(tmp_path) -> None:
    raw = _import_replay(1)
    rows = [json.loads(line) for line in (raw + b"\n").splitlines()]
    journal_id = rows[0]["id"]
    store = ExplorationStore(tmp_path / "store")
    store.directory.mkdir()
    target = tmp_path / "outside.jsonl"
    target.write_bytes(b"leave this alone")
    link = store._journal_path(journal_id)
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this machine")

    with pytest.raises(ExplorationConflictError):
        store.import_bytes(raw)
    assert target.read_bytes() == b"leave this alone"


def test_import_rejects_unrepresentable_capture_time_before_writing(tmp_path) -> None:
    rows = [json.loads(line) for line in (_import_replay(1) + b"\n").splitlines()]
    rows[1]["snapshot"]["captured_at"] = 1e20
    invalid = b"\n".join(json.dumps(row).encode() for row in rows)
    directory = tmp_path / "unrepresentable"
    store = ExplorationStore(directory)

    with pytest.raises(CorruptExplorationError):
        store.import_bytes(invalid)

    assert not directory.exists()
