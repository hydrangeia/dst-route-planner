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


def test_segment_ids_keep_legacy_identity_for_part_one() -> None:
    import hashlib

    legacy = hashlib.sha256(b'["world-abc","forest","session-1"]').hexdigest()
    assert exploration_id("world-abc", "forest", "session-1") == legacy
    assert exploration_id("world-abc", "forest", "session-1", segment=1) == legacy
    assert exploration_id("world-abc", "forest", "session-1", segment=2) == hashlib.sha256(
        b'["world-abc","forest","session-1",2]'
    ).hexdigest()
    assert exploration_id("world-abc", "forest", "session-1", segment=2) != legacy


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


def test_separate_processes_share_session_lock_during_rollover(tmp_path, monkeypatch) -> None:
    import dst_route_planner.exploration as exploration

    monkeypatch.setattr(exploration, "MAX_EXPLORATION_FRAMES", 1)
    _capture(
        ExplorationStore(tmp_path),
        1,
        world_id="process-rollover-world",
        session_id="process-rollover-session",
    )
    script = r'''
import json, sys, time
import dst_route_planner.exploration as exploration
from dst_route_planner.exploration import ExplorationStore

exploration.MAX_EXPLORATION_FRAMES = 1
snapshot = {
    "live_version": 1,
    "world_id": "process-rollover-world",
    "world_kind": "forest",
    "session_id": "process-rollover-session",
    "sequence": 2,
    "captured_at": time.time(),
    "position": {"x": 2, "y": 0, "z": 0},
    "camera_heading": 0,
    "current": {"schema_version": 1, "tile_types": ["GRASS"]},
    "directions": __import__("dst_route_planner.app", fromlist=["_demo"])._demo()["directions"],
}
print(json.dumps(ExplorationStore(sys.argv[1]).capture(snapshot, target="panflute", seed=0)))
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
    assert {summary["id"] for summary in summaries} == {
        exploration_id(
            "process-rollover-world",
            "forest",
            "process-rollover-session",
            segment=2,
        )
    }
    assert all(summary["frame_count"] == 1 and summary["segment"] == 2 for summary in summaries)
    assert len(list(tmp_path.glob("*.jsonl"))) == 2
    part2 = tmp_path / f"{summaries[0]['id']}.jsonl"
    assert [json.loads(line)["snapshot"]["sequence"] for line in part2.read_bytes().splitlines()[1:]] == [2]


def test_frame_and_byte_limits_roll_over_without_changing_old_parts(tmp_path, monkeypatch) -> None:
    import dst_route_planner.exploration as exploration

    store = ExplorationStore(tmp_path)
    monkeypatch.setattr(exploration, "MAX_EXPLORATION_FRAMES", 2)
    first = _capture(store, 1)
    second = _capture(store, 2)
    path = tmp_path / f"{first['id']}.jsonl"
    original_first_part = path.read_bytes()

    assert second["status"] == "limit_reached"
    third = _capture(store, 3)
    assert third["status"] == "recording"
    assert third["segment"] == 2
    assert third["frame_count"] == 1
    assert path.read_bytes() == original_first_part
    second_path = tmp_path / f"{third['id']}.jsonl"
    assert [json.loads(line)["snapshot"]["sequence"] for line in second_path.read_bytes().splitlines()[1:]] == [3]

    monkeypatch.setattr(exploration, "MAX_EXPLORATION_FRAMES", 10_000)
    byte_store_dir = tmp_path / "bytes"
    byte_store = ExplorationStore(byte_store_dir)
    byte_first = _capture(byte_store, 1, world_id="byte-world", session_id="byte-session")
    byte_path = byte_store_dir / f"{byte_first['id']}.jsonl"
    byte_original = byte_path.read_bytes()
    monkeypatch.setattr(exploration, "MAX_EXPLORATION_BYTES", len(byte_original) + 128)
    byte_second = _capture(byte_store, 2, world_id="byte-world", session_id="byte-session")

    assert byte_second["segment"] == 2
    assert byte_second["status"] == "recording"
    assert byte_path.read_bytes() == byte_original
    byte_part2 = byte_store_dir / f"{byte_second['id']}.jsonl"
    assert [json.loads(line)["snapshot"]["sequence"] for line in byte_part2.read_bytes().splitlines()[1:]] == [2]


def _import_replay(
    *sequences: int,
    world_id: str = "import-world",
    session_id: str = "import-session",
    segment: int = 1,
) -> bytes:
    world_kind = "forest"
    journal_id = exploration_id(world_id, world_kind, session_id, segment=segment)
    header = {
        "replay_version": 1,
        "id": journal_id,
        "world_id": world_id,
        "world_kind": world_kind,
        "session_id": session_id,
    }
    if segment >= 2:
        header["segment"] = segment
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


def test_full_active_part_rolls_once_and_active_summary_follows_it(tmp_path, monkeypatch) -> None:
    import dst_route_planner.exploration as exploration

    monkeypatch.setattr(exploration, "MAX_EXPLORATION_FRAMES", 1)
    store = ExplorationStore(tmp_path)
    first = _capture(store, 1)
    first_path = tmp_path / f"{first['id']}.jsonl"
    first_bytes = first_path.read_bytes()
    second = _capture(store, 2)
    second_path = tmp_path / f"{second['id']}.jsonl"
    second_bytes = second_path.read_bytes()

    assert second["segment"] == 2
    assert store.summary_for_snapshot(_snapshot(3)) == second
    assert _capture(store, 2) == second
    assert _capture(store, 1) == second
    assert first_path.read_bytes() == first_bytes
    assert second_path.read_bytes() == second_bytes
    assert {path.stem for path in tmp_path.glob("*.jsonl")} == {first["id"], second["id"]}


def test_imported_sibling_parts_coexist_and_only_exact_id_conflicts(tmp_path) -> None:
    store = ExplorationStore(tmp_path)
    legacy_raw = _import_replay(1, 2)
    part2_raw = _import_replay(3, 4, segment=2)
    legacy, legacy_created = store.import_bytes(legacy_raw)
    part2, part2_created = store.import_bytes(part2_raw)

    assert legacy_created is True
    assert part2_created is True
    assert part2["segment"] == 2
    assert len(store.list_explorations()) == 2
    assert store.get_bytes(legacy["id"]) == legacy_raw + b"\n"
    assert store.get_bytes(part2["id"]) == part2_raw + b"\n"

    changed_rows = [json.loads(line) for line in (part2_raw + b"\n").splitlines()]
    changed_rows[1]["target"] = "pigking"
    changed = b"\n".join(json.dumps(row).encode() for row in changed_rows)
    with pytest.raises(ExplorationConflictError):
        store.import_bytes(changed)


@pytest.mark.parametrize(
    ("first_segment", "first_sequences", "second_segment", "second_sequences"),
    [
        (2, (3, 4), 1, (10,)),
        (1, (10,), 2, (3, 4)),
    ],
)
def test_import_rejects_reversed_or_overlapping_sibling_sequence_ranges(
    tmp_path,
    first_segment,
    first_sequences,
    second_segment,
    second_sequences,
) -> None:
    store = ExplorationStore(tmp_path)
    first_raw = _import_replay(*first_sequences, segment=first_segment)
    second_raw = _import_replay(*second_sequences, segment=second_segment)
    first_summary, created = store.import_bytes(first_raw)
    first_path = tmp_path / f"{first_summary['id']}.jsonl"
    original = first_path.read_bytes()

    assert created is True
    with pytest.raises(ExplorationConflictError, match="sequence ranges"):
        store.import_bytes(second_raw)

    duplicate, duplicate_created = store.import_bytes(first_raw)
    assert duplicate == first_summary
    assert duplicate_created is False
    assert first_path.read_bytes() == original
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_import_accepts_noncontiguous_sibling_ranges_in_either_order(tmp_path) -> None:
    earlier = _import_replay(1, 2, world_id="gap-world", session_id="gap-session")
    later = _import_replay(
        7,
        9,
        world_id="gap-world",
        session_id="gap-session",
        segment=2,
    )
    for order in ((earlier, later), (later, earlier)):
        store = ExplorationStore(tmp_path / str(len(list(tmp_path.iterdir()))))
        summaries = [store.import_bytes(raw)[0] for raw in order]
        assert {summary.get("segment", 1) for summary in summaries} == {1, 2}
        assert len(store.list_explorations()) == 2


def test_sparse_imported_part_resumes_after_store_restart(tmp_path) -> None:
    imported_raw = _import_replay(1, 2, world_id="sparse-world", session_id="sparse-session", segment=7)
    first_store = ExplorationStore(tmp_path)
    imported, created = first_store.import_bytes(imported_raw)
    assert created is True
    assert imported["segment"] == 7

    restarted = ExplorationStore(tmp_path)
    continued = _capture(
        restarted,
        3,
        world_id="sparse-world",
        session_id="sparse-session",
    )
    journal = [json.loads(line) for line in restarted.get_bytes(continued["id"]).splitlines()]

    assert continued["id"] == imported["id"]
    assert continued["segment"] == 7
    assert continued["frame_count"] == 3
    assert [row.get("snapshot", {}).get("sequence") for row in journal[1:]] == [1, 2, 3]
    assert journal[0]["segment"] == 7
    assert restarted.summary_for_snapshot(
        _snapshot(4, world_id="sparse-world", session_id="sparse-session")
    ) == continued


def test_segment_header_rejects_noncanonical_values(tmp_path) -> None:
    valid = _import_replay(1, segment=2)
    rows = [json.loads(line) for line in (valid + b"\n").splitlines()]
    invalid_segments = (True, 2.0, 0, 1, 2**53)

    for segment in invalid_segments:
        changed = copy.deepcopy(rows)
        changed[0]["segment"] = segment
        raw = b"\n".join(json.dumps(row).encode() for row in changed)
        with pytest.raises(CorruptExplorationError):
            ExplorationStore(tmp_path / str(len(list(tmp_path.iterdir())))).import_bytes(raw)

    with pytest.raises(ValueError):
        exploration_id("world", "forest", "session", segment=True)
    with pytest.raises(ValueError):
        exploration_id("world", "forest", "session", segment=2.0)
    with pytest.raises(ValueError):
        exploration_id("world", "forest", "session", segment=0)
    with pytest.raises(ValueError):
        exploration_id("world", "forest", "session", segment=2**53)
    assert len(exploration_id("world", "forest", "session", segment=2**53 - 1)) == 64


def test_too_large_first_frame_does_not_create_empty_segments(tmp_path, monkeypatch) -> None:
    import dst_route_planner.exploration as exploration

    store = ExplorationStore(tmp_path)
    monkeypatch.setattr(exploration, "MAX_EXPLORATION_BYTES", 10)
    rejected = _capture(store, 1)

    assert rejected["frame_count"] == 0
    assert rejected["status"] == "limit_reached"
    assert list(tmp_path.glob("*.jsonl")) == []

    monkeypatch.setattr(exploration, "MAX_EXPLORATION_BYTES", 32 * 1024 * 1024)
    recorded = _capture(store, 1)
    assert recorded.get("segment") is None
    assert recorded["frame_count"] == 1
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_frame_that_fits_part_one_but_not_longer_part_header_stays_active(tmp_path, monkeypatch) -> None:
    import dst_route_planner.exploration as exploration

    fixed_received_at = "2026-02-01T00:00:00.000000Z"
    monkeypatch.setattr(exploration, "_timestamp", lambda: fixed_received_at)
    first_snapshot = _snapshot(1)
    second_snapshot = _snapshot(2)
    first_snapshot["captured_at"] = 1_770_000_000.0
    second_snapshot["captured_at"] = 1_770_000_000.0
    frame_bytes = exploration._json_line(
        {
            "replay_version": 1,
            "received_at": fixed_received_at,
            "target": "panflute",
            "seed": 13,
            "snapshot": exploration.validate_snapshot(second_snapshot),
            "plan": {"target": "panflute", "seed": 13},
        }
    )
    first_header = exploration._json_line(
        exploration.ExplorationStore._make_header("world-abc", "forest", "session-1")
    )
    second_header = exploration._json_line(
        exploration.ExplorationStore._make_header(
            "world-abc", "forest", "session-1", segment=2
        )
    )
    assert len(first_header) + len(frame_bytes) < len(second_header) + len(frame_bytes)

    store = ExplorationStore(tmp_path)
    first = store.capture(
        first_snapshot,
        target="panflute",
        seed=13,
        plan={"target": "panflute", "seed": 13},
    )
    path = tmp_path / f"{first['id']}.jsonl"
    original = path.read_bytes()
    assert len(original) == len(first_header) + len(frame_bytes)
    monkeypatch.setattr(exploration, "MAX_EXPLORATION_BYTES", len(original))

    result = store.capture(
        second_snapshot,
        target="panflute",
        seed=13,
        plan={"target": "panflute", "seed": 13},
    )

    assert result["id"] == first["id"]
    assert result.get("segment") is None
    assert result["status"] == "limit_reached"
    assert path.read_bytes() == original
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_max_segment_capacity_returns_cleanly_without_overflow(tmp_path, monkeypatch) -> None:
    import dst_route_planner.exploration as exploration

    maximum = exploration.MAX_EXPLORATION_SEGMENT
    store = ExplorationStore(tmp_path)
    raw = _import_replay(
        1,
        world_id="max-segment-world",
        session_id="max-segment-session",
        segment=maximum,
    )
    imported, _ = store.import_bytes(raw)
    path = tmp_path / f"{imported['id']}.jsonl"
    original = path.read_bytes()
    monkeypatch.setattr(exploration, "MAX_EXPLORATION_FRAMES", 1)

    result = _capture(
        store,
        2,
        world_id="max-segment-world",
        session_id="max-segment-session",
    )

    assert result["id"] == imported["id"]
    assert result["segment"] == maximum
    assert result["status"] == "limit_reached"
    assert path.read_bytes() == original
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_concurrent_stores_roll_over_to_one_shared_part(tmp_path, monkeypatch) -> None:
    import dst_route_planner.exploration as exploration

    monkeypatch.setattr(exploration, "MAX_EXPLORATION_FRAMES", 1)
    _capture(ExplorationStore(tmp_path), 1)
    stores = [ExplorationStore(tmp_path) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda store: _capture(store, 2), stores))

    assert len({result["id"] for result in results}) == 1
    assert all(result["segment"] == 2 and result["frame_count"] == 1 for result in results)
    assert len(list(tmp_path.glob("*.jsonl"))) == 2
    part2 = tmp_path / f"{results[0]['id']}.jsonl"
    assert [json.loads(line)["snapshot"]["sequence"] for line in part2.read_bytes().splitlines()[1:]] == [2]


def test_segment_index_refreshes_from_headers_without_reparsing_cached_bodies(
    tmp_path, monkeypatch
) -> None:
    store = ExplorationStore(tmp_path)
    _capture(store, 1, world_id="indexed-world", session_id="indexed-session")
    store.summary_for_snapshot(
        _snapshot(2, world_id="indexed-world", session_id="indexed-session")
    )
    parse_count = 0
    original_reader = store._read_journal_bytes

    def count_parse(*args, **kwargs):
        nonlocal parse_count
        parse_count += 1
        return original_reader(*args, **kwargs)

    monkeypatch.setattr(store, "_read_journal_bytes", count_parse)
    assert _capture(store, 2, world_id="indexed-world", session_id="indexed-session")["frame_count"] == 2
    assert store.summary_for_snapshot(
        _snapshot(3, world_id="indexed-world", session_id="indexed-session")
    )["frame_count"] == 2
    assert parse_count == 0

    sparse = _import_replay(
        10,
        world_id="indexed-world",
        session_id="indexed-session",
        segment=5,
    )
    ExplorationStore(tmp_path).import_bytes(sparse)
    resumed = _capture(store, 11, world_id="indexed-world", session_id="indexed-session")
    assert resumed["segment"] == 5
    assert resumed["frame_count"] == 2
    assert parse_count == 1

    store.summary_for_snapshot(
        _snapshot(12, world_id="indexed-world", session_id="indexed-session")
    )
    _capture(store, 12, world_id="indexed-world", session_id="indexed-session")
    assert parse_count == 1
