from __future__ import annotations

import json
import uuid

import pytest

from dst_route_planner.records import (
    CorruptRecordError,
    InvalidRecordIdError,
    RecordNotFoundError,
    RecordStore,
)


def _observation(note: str = "north path") -> dict:
    return {
        "schema_version": 1,
        "target": "panflute",
        "seed": 17,
        "directions": {
            "north": {
                "tile_types": ["DECIDUOUS"],
                "prefabs_seen": ["pigking"],
                "note": note,
            }
        },
        "current": {"schema_version": 1, "tile_types": ["GRASS"], "note": "near spawn"},
    }


def test_records_survive_store_restart_and_updates_keep_one_record(tmp_path) -> None:
    first_store = RecordStore(tmp_path / "records")
    original, created = first_store.save(
        name="  Autumn world  ",
        world_note="Wendy, day 12",
        observation=_observation(),
    )

    assert created is True
    assert original["name"] == "Autumn world"
    assert original["observation"] == _observation()
    restarted_store = RecordStore(tmp_path / "records")
    assert restarted_store.get(original["id"]) == original
    assert restarted_store.list_records() == [
        {
            "id": original["id"],
            "name": "Autumn world",
            "target": "panflute",
            "saved_at": original["saved_at"],
        }
    ]

    updated, created = restarted_store.save(
        record_id=original["id"],
        name="Autumn world, day 20",
        world_note="Found the swamp edge",
        observation=_observation("looked beyond the swamp"),
    )

    assert created is False
    assert updated["id"] == original["id"]
    assert updated["name"] == "Autumn world, day 20"
    assert updated["world_note"] == "Found the swamp edge"
    assert updated["observation"]["directions"]["north"]["note"] == "looked beyond the swamp"
    assert restarted_store.list_records()[0]["name"] == "Autumn world, day 20"
    assert len(list((tmp_path / "records").glob("*.json"))) == 1


def test_missing_or_malformed_record_ids_are_rejected(tmp_path) -> None:
    store = RecordStore(tmp_path / "records")
    missing_id = str(uuid.uuid4())

    with pytest.raises(RecordNotFoundError):
        store.get(missing_id)
    with pytest.raises(RecordNotFoundError):
        store.save(
            record_id=missing_id,
            name="Missing",
            world_note="",
            observation=_observation(),
        )
    with pytest.raises(InvalidRecordIdError):
        store.get("../../outside")
    with pytest.raises(InvalidRecordIdError):
        store.save(
            record_id="../../outside",
            name="Unsafe",
            world_note="",
            observation=_observation(),
        )


def test_failed_atomic_replace_leaves_previous_record_intact(tmp_path, monkeypatch) -> None:
    store = RecordStore(tmp_path / "records")
    original, _ = store.save(name="Original", world_note="", observation=_observation())

    def fail_replace(source, destination):
        raise OSError("simulated disk error")

    monkeypatch.setattr("dst_route_planner.records.os.replace", fail_replace)
    with pytest.raises(OSError, match="simulated disk error"):
        store.save(
            record_id=original["id"],
            name="Replacement",
            world_note="new note",
            observation=_observation("new observation"),
        )

    assert store.get(original["id"]) == original
    assert not list((tmp_path / "records").glob("*.tmp"))


def test_listing_skips_unknown_and_corrupt_files_but_selected_corruption_is_reported(tmp_path) -> None:
    directory = tmp_path / "records"
    store = RecordStore(directory)
    valid, _ = store.save(name="Kept", world_note="", observation=_observation())
    (directory / "notes.json").write_text("not a record", encoding="utf-8")
    corrupt_id = str(uuid.uuid4())
    (directory / f"{corrupt_id}.json").write_text('{"record_version":', encoding="utf-8")

    assert [item["id"] for item in store.list_records()] == [valid["id"]]
    with pytest.raises(CorruptRecordError):
        store.get(corrupt_id)


def test_saved_record_metadata_limits_are_checked(tmp_path) -> None:
    store = RecordStore(tmp_path / "records")
    with pytest.raises(ValueError, match="name"):
        store.save(name=" \t ", world_note="", observation=_observation())
    with pytest.raises(ValueError, match="120 characters"):
        store.save(name="x" * 121, world_note="", observation=_observation())
    with pytest.raises(ValueError, match="world_note"):
        store.save(name="Valid", world_note=object(), observation=_observation())
    with pytest.raises(ValueError, match="4096 characters"):
        store.save(name="Valid", world_note="x" * 4097, observation=_observation())
