from __future__ import annotations

import copy
import http.client
import json
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from dst_route_planner import app
from dst_route_planner.live import LIVE_MARKER


@pytest.fixture
def local_server(monkeypatch):
    temporary_dir = TemporaryDirectory(prefix=".test-local-app-", dir=app.PACKAGE_DIR)
    html_path = Path(temporary_dir.name) / "app.html"
    html_path.write_text("<!doctype html><title>route planner test</title>", encoding="utf-8")
    monkeypatch.setattr(app, "APP_HTML_PATH", html_path)
    record_dir = Path(temporary_dir.name) / "records"
    server = app.create_server(port=0, record_dir=record_dir)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}", server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        temporary_dir.cleanup()


def _get(base_url: str, path: str):
    try:
        response = urlopen(base_url + path, timeout=5)
    except HTTPError as error_response:
        response = error_response
    with response:
        body = response.read().decode("utf-8")
        if response.headers.get_content_type() == "application/json":
            body = json.loads(body)
        return response.status, response.headers, body


def _post(base_url: str, payload: bytes | dict, path: str = "/api/plan"):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    request = Request(
        base_url + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            return response.status, response.headers, json.loads(response.read().decode("utf-8"))
    except HTTPError as response:
        return response.code, response.headers, json.loads(response.read().decode("utf-8"))


def test_create_server_binds_to_loopback_and_serves_static_page(local_server) -> None:
    base_url, server = local_server
    status, headers, body = _get(base_url, "/")

    assert server.server_address[0] == "127.0.0.1"
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert "route planner test" in body


def test_options_and_demo_endpoints_return_usable_manual_input(local_server) -> None:
    base_url, _ = local_server
    status, _, options = _get(base_url, "/api/options")
    demo_status, _, demo = _get(base_url, "/api/demo")

    assert status == 200
    assert options["targets"] == sorted(set(options["targets"]))
    assert "panflute" in options["targets"]
    assert "DECIDUOUS" in options["tile_types"]
    assert "panflute" in options["prefabs"]
    assert options["directions"] == [
        "north",
        "northeast",
        "east",
        "southeast",
        "south",
        "southwest",
        "west",
        "northwest",
    ]
    assert demo_status == 200
    assert demo["schema_version"] == 1
    assert demo["target"] == "panflute"
    assert demo["seed"] == 0
    assert set(demo["directions"]) == {"north", "east", "south", "west"}


def test_plan_endpoint_returns_ranked_directions_and_current_beliefs(local_server) -> None:
    base_url, _ = local_server
    _, _, demo = _get(base_url, "/api/demo")
    payload = dict(demo)
    payload["current"] = {"schema_version": 1, "tile_types": ["GRASS"]}

    status, headers, result = _post(base_url, payload)

    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    assert result["target"] == "panflute"
    assert result["seed"] == 0
    assert {"direction", "score", "p_dir", "p_task", "p_room", "explanation"} <= set(
        result["directions"][0]
    )
    assert len(result["directions"]) == 4
    assert sum(item["p_dir"] for item in result["directions"]) == pytest.approx(1.0)
    assert all(isinstance(item["explanation"], list) for item in result["directions"])
    assert result["current_tasks"]
    assert {"name", "probability"} == set(result["current_tasks"][0])


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p: p.update(target="not_a_target"), "unknown target"),
        (lambda p: p.update(seed=True), "seed must be an integer"),
        (lambda p: p.update(schema_version=2), "schema_version 1"),
        (lambda p: p["directions"].update(sideways={}), "unknown direction"),
        (
            lambda p: p["directions"]["north"].update(prefab_counts={"flower": 1.25}),
            "non-negative integer",
        ),
    ],
)
def test_invalid_plan_payloads_return_human_readable_400(local_server, mutate, message) -> None:
    base_url, _ = local_server
    _, _, demo = _get(base_url, "/api/demo")
    payload = copy.deepcopy(demo)
    mutate(payload)

    status, _, body = _post(base_url, payload)

    assert status == 400
    assert message in body["error"]
    assert "Traceback" not in body["error"]


def test_http_errors_cover_bad_json_size_and_missing_content_type(local_server) -> None:
    base_url, _ = local_server
    status, _, invalid_json = _post(base_url, b"{")
    assert status == 400
    assert "invalid JSON" in invalid_json["error"]

    _, server = local_server
    connection = http.client.HTTPConnection(*server.server_address[:2], timeout=5)
    connection.putrequest("POST", "/api/plan")
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", str(app.MAX_REQUEST_BYTES + 1))
    connection.endheaders()
    response = connection.getresponse()
    too_large = json.loads(response.read().decode("utf-8"))
    assert response.status == 413
    assert "limit" in too_large["error"]
    connection.close()

    request = Request(base_url + "/api/plan", data=b"{}", method="POST")
    try:
        urlopen(request, timeout=5)
    except HTTPError as response:
        assert response.code == 400
        assert "Content-Type" in response.read().decode("utf-8")
    else:
        pytest.fail("expected a content type validation error")


def test_server_does_not_enable_wildcard_cross_origin_access(local_server) -> None:
    base_url, _ = local_server
    _, headers, _ = _get(base_url, "/api/options")

    assert headers.get("Access-Control-Allow-Origin") is None



def _record_payload(observation: dict) -> dict:
    return {
        "record_version": 1,
        "name": "  Autumn world  ",
        "world_note": "Wendy, day 12",
        "observation": copy.deepcopy(observation),
    }


def test_records_api_creates_lists_reads_updates_and_survives_server_restart(
    local_server, monkeypatch
) -> None:
    base_url, server = local_server
    _, _, demo = _get(base_url, "/api/demo")
    payload = _record_payload(demo)

    def inference_must_not_run(*args, **kwargs):
        raise AssertionError("saving a record must not run planner inference")

    monkeypatch.setattr(app, "initial_belief", inference_must_not_run)
    status, _, created = _post(base_url, payload, path="/api/records")
    assert status == 201
    assert created["record_version"] == 1
    assert created["name"] == "Autumn world"
    assert created["world_note"] == "Wendy, day 12"
    assert created["observation"] == demo

    list_status, _, listing = _get(base_url, "/api/records")
    assert list_status == 200
    assert listing == {
        "records": [
            {
                "id": created["id"],
                "name": "Autumn world",
                "target": "panflute",
                "saved_at": created["saved_at"],
            }
        ]
    }
    detail_status, _, detail = _get(base_url, f"/api/records/{created['id']}")
    assert detail_status == 200
    assert detail == created

    updated_payload = _record_payload(demo)
    updated_payload.update(id=created["id"], name="Autumn world, day 20", world_note="Swamp edge found")
    update_status, _, updated = _post(base_url, updated_payload, path="/api/records")
    assert update_status == 200
    assert updated["id"] == created["id"]
    assert updated["name"] == "Autumn world, day 20"
    assert updated["world_note"] == "Swamp edge found"

    record_dir = server.record_store.directory
    restarted_server = app.create_server(port=0, record_dir=record_dir)
    restarted_thread = threading.Thread(target=restarted_server.serve_forever, daemon=True)
    restarted_thread.start()
    host, port = restarted_server.server_address[:2]
    try:
        restart_status, _, persisted = _get(f"http://{host}:{port}", f"/api/records/{created['id']}")
        assert restart_status == 200
        assert persisted == updated
    finally:
        restarted_server.shutdown()
        restarted_server.server_close()
        restarted_thread.join(timeout=2)


def test_invalid_record_saves_and_missing_updates_do_not_change_saved_data(local_server) -> None:
    base_url, _ = local_server
    _, _, demo = _get(base_url, "/api/demo")
    payload = _record_payload(demo)
    status, _, saved = _post(base_url, payload, path="/api/records")
    assert status == 201

    invalid_update = copy.deepcopy(payload)
    invalid_update.update(id=saved["id"], name="Changed")
    invalid_update["observation"]["directions"]["north"]["prefab_counts"] = {"pigking": 1.5}
    status, _, error = _post(base_url, invalid_update, path="/api/records")
    assert status == 400
    assert "non-negative integer" in error["error"]
    detail_status, _, detail = _get(base_url, f"/api/records/{saved['id']}")
    assert detail_status == 200
    assert detail == saved

    missing_update = copy.deepcopy(payload)
    missing_update["id"] = "00000000-0000-4000-8000-000000000001"
    missing_status, _, missing = _post(base_url, missing_update, path="/api/records")
    assert missing_status == 404
    assert "not found" in missing["error"]


def test_records_api_validates_metadata_ids_and_corrupt_files(local_server) -> None:
    base_url, server = local_server
    _, _, demo = _get(base_url, "/api/demo")

    payload = _record_payload(demo)
    payload["name"] = " "
    status, _, error = _post(base_url, payload, path="/api/records")
    assert status == 400
    assert "name" in error["error"]

    payload = _record_payload(demo)
    payload["world_note"] = "x" * 4097
    status, _, error = _post(base_url, payload, path="/api/records")
    assert status == 400
    assert "4096" in error["error"]

    invalid_id_status, _, invalid_id = _get(base_url, "/api/records/not-a-uuid")
    assert invalid_id_status == 400
    assert "UUID" in invalid_id["error"]
    absent_status, _, absent = _get(
        base_url, "/api/records/00000000-0000-4000-8000-000000000002"
    )
    assert absent_status == 404
    assert "not found" in absent["error"]

    _, _, saved = _post(base_url, _record_payload(demo), path="/api/records")
    corrupt_id = "00000000-0000-4000-8000-000000000003"
    server.record_store.directory.mkdir(parents=True, exist_ok=True)
    (server.record_store.directory / f"{corrupt_id}.json").write_text("{", encoding="utf-8")
    (server.record_store.directory / "leftover.json").write_text("not JSON", encoding="utf-8")

    listing_status, _, listing = _get(base_url, "/api/records")
    assert listing_status == 200
    assert [row["id"] for row in listing["records"]] == [saved["id"]]
    corrupt_status, _, corrupt = _get(base_url, f"/api/records/{corrupt_id}")
    assert corrupt_status == 500
    assert "could not be read" in corrupt["error"]



def _live_snapshot(
    observation: dict,
    captured_at: float | None = None,
    *,
    sequence: int = 1,
    world_id: str = "world-abc",
    world_kind: str = "forest",
    session_id: str = "session-1",
) -> dict:
    return {
        "live_version": 1,
        "world_id": world_id,
        "world_kind": world_kind,
        "session_id": session_id,
        "sequence": sequence,
        "captured_at": time.time() if captured_at is None else captured_at,
        "position": {"x": 0, "y": 0, "z": 0},
        "camera_heading": 270.0,
        "current": {"schema_version": 1, "tile_types": ["GRASS"], "note": "near spawn"},
        "directions": copy.deepcopy(observation),
        "landmarks": [
            {"prefab": "panflute", "x": 3, "z": 4},
            {"prefab": "panflute", "x": 1, "z": 1},
            {"prefab": "pigking", "x": 0, "z": 2},
        ],
    }


def _write_live_snapshot(path: Path, snapshot: dict, *, prefix: str = "") -> None:
    path.write_text(
        f"{prefix}{LIVE_MARKER}{json.dumps(snapshot, separators=(',', ':'))}\n",
        encoding="utf-8",
    )


def test_live_endpoint_disabled_waiting_and_query_validation(local_server) -> None:
    base_url, server = local_server
    disabled_status, _, disabled = _get(base_url, "/api/live?target=panflute&seed=0")
    assert disabled_status == 200
    assert disabled == {"status": "disabled"}

    live_log = server.record_store.directory.parent / "client.log"
    server.live_log = live_log
    waiting_status, _, waiting = _get(base_url, "/api/live?target=panflute&seed=0")
    assert waiting_status == 200
    assert waiting == {"status": "waiting"}

    bad_target_status, _, bad_target = _get(base_url, "/api/live?target=unknown&seed=0")
    assert bad_target_status == 400
    assert "unknown target" in bad_target["error"]
    bad_seed_status, _, bad_seed = _get(base_url, "/api/live?target=panflute&seed=not-a-number")
    assert bad_seed_status == 400
    assert "seed must be an integer" in bad_seed["error"]
    duplicate_status, _, duplicate = _get(
        base_url, "/api/live?target=panflute&target=moonbase&seed=0"
    )
    assert duplicate_status == 400
    assert "target must be supplied at most once" in duplicate["error"]


def test_live_endpoint_uses_current_position_for_plan_and_nearest_target(local_server) -> None:
    base_url, server = local_server
    _, _, demo = _get(base_url, "/api/demo")
    directions = copy.deepcopy(demo["directions"])
    directions["north"].setdefault("prefab_counts", {})["panflute"] = 1
    snapshot = _live_snapshot(directions)
    live_log = server.record_store.directory.parent / "client.log"
    _write_live_snapshot(live_log, snapshot, prefix="[client timestamp] ")
    server.live_log = live_log

    status, _, response = _get(base_url, "/api/live?target=panflute&seed=0")

    assert status == 200
    assert response["status"] == "live"
    assert response["snapshot"] == snapshot
    assert response["age_seconds"] <= 5
    expected_plan = app._plan_request(
        {
            "schema_version": 1,
            "target": "panflute",
            "seed": 0,
            "current": snapshot["current"],
            "directions": snapshot["directions"],
        }
    )
    assert response["plan"] == expected_plan
    assert response["plan"]["target"] == "panflute"
    assert len(response["plan"]["directions"]) == 4
    assert response["visible_target"] == {
        "prefab": "panflute",
        "x": 1,
        "z": 1,
        "distance": pytest.approx(2**0.5),
    }
    recording = response["recording"]
    assert recording["status"] == "recording"
    assert recording["frame_count"] == 1
    assert recording["world_id"] == snapshot["world_id"]
    assert recording["world_kind"] == snapshot["world_kind"]
    assert recording["session_id"] == snapshot["session_id"]
    assert isinstance(recording["started_at"], str)
    assert isinstance(recording["last_captured_at"], str)

    list_status, _, listing = _get(base_url, "/api/explorations")
    assert list_status == 200
    assert listing["explorations"] == [recording]
    download_status, download_headers, download = _get(
        base_url, f"/api/explorations/{recording['id']}"
    )
    assert download_status == 200
    assert download_headers.get_content_type() == "application/x-ndjson"
    assert download_headers["Content-Disposition"] == (
        f"attachment; filename=\"dst-exploration-{recording['id']}.jsonl\""
    )
    assert download.encode("utf-8") == server.exploration_store.get_bytes(recording["id"])
    journal_path = server.exploration_store._journal_path(recording["id"])
    complete_journal = journal_path.read_bytes()
    partial_tail = b'{"replay_version":1,"snapshot":'
    journal_path.write_bytes(complete_journal + partial_tail)
    partial_download_status, _, partial_download = _get(
        base_url, f"/api/explorations/{recording['id']}"
    )
    assert partial_download_status == 200
    assert partial_download.encode("utf-8") == complete_journal
    assert journal_path.read_bytes() == complete_journal + partial_tail

    invalid_id_status, _, invalid_id = _get(base_url, "/api/explorations/not-a-safe-id")
    assert invalid_id_status == 400
    assert "64-character lowercase hexadecimal" in invalid_id["error"]
    missing_status, _, missing = _get(base_url, "/api/explorations/" + "0" * 64)
    assert missing_status == 404
    assert "not found" in missing["error"]


def test_live_stale_and_cave_snapshots_never_run_inference(local_server, monkeypatch) -> None:
    base_url, server = local_server
    live_log = server.record_store.directory.parent / "client.log"
    server.live_log = live_log

    _, _, demo = _get(base_url, "/api/demo")
    fresh = _live_snapshot(demo["directions"])
    _write_live_snapshot(live_log, fresh)
    fresh_status, _, fresh_result = _get(base_url, "/api/live?target=panflute&seed=0")
    assert fresh_status == 200
    saved_id = fresh_result["recording"]["id"]
    saved_path = server.exploration_store._journal_path(saved_id)
    saved_bytes = saved_path.read_bytes()

    def inference_must_not_run(*args, **kwargs):
        raise AssertionError("stale or unsupported snapshots must not run inference")

    monkeypatch.setattr(app, "_plan_request", inference_must_not_run)
    cave = _live_snapshot(demo["directions"], world_kind="cave")
    _write_live_snapshot(live_log, cave)
    cave_status, _, cave_result = _get(base_url, "/api/live?target=panflute&seed=0")
    assert cave_status == 200
    assert cave_result["status"] == "unsupported_world"
    assert "plan" not in cave_result
    assert cave_result["recording"]["status"] == "recording"
    assert cave_result["recording"]["frame_count"] == 1
    cave_id = cave_result["recording"]["id"]
    cave_path = server.exploration_store._journal_path(cave_id)
    cave_bytes = cave_path.read_bytes()
    stale_cave = _live_snapshot(
        demo["directions"], captured_at=time.time() - 10, world_kind="cave"
    )
    _write_live_snapshot(live_log, stale_cave)
    stale_cave_status, _, stale_cave_result = _get(
        base_url, "/api/live?target=panflute&seed=0"
    )
    assert stale_cave_status == 200
    assert stale_cave_result["status"] == "unsupported_world"
    assert stale_cave_result["age_seconds"] > 5
    assert stale_cave_result["recording"]["id"] == cave_id
    assert stale_cave_result["recording"]["frame_count"] == 1
    assert cave_path.read_bytes() == cave_bytes

    stale = _live_snapshot(demo["directions"], captured_at=time.time() - 10)
    _write_live_snapshot(live_log, stale)
    stale_status, _, stale_result = _get(base_url, "/api/live?target=panflute&seed=0")
    assert stale_status == 200
    assert stale_result["status"] == "stale"
    assert stale_result["age_seconds"] > 5
    assert "plan" not in stale_result
    assert stale_result["recording"]["id"] == saved_id
    assert stale_result["recording"]["frame_count"] == 1
    assert saved_path.read_bytes() == saved_bytes


def test_live_recording_disk_failure_does_not_break_position_or_plan(local_server, monkeypatch) -> None:
    base_url, server = local_server
    _, _, demo = _get(base_url, "/api/demo")
    snapshot = _live_snapshot(demo["directions"])
    live_log = server.record_store.directory.parent / "client.log"
    _write_live_snapshot(live_log, snapshot)
    server.live_log = live_log

    def disk_failure(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(server.exploration_store, "capture", disk_failure)
    status, _, result = _get(base_url, "/api/live?target=panflute&seed=0")

    assert status == 200
    assert result["status"] == "live"
    assert result["snapshot"]["position"] == snapshot["position"]
    assert "plan" in result
    assert result["recording"]["status"] == "error"
    assert result["recording"]["error"] == "disk full"


def test_live_endpoint_returns_error_for_malformed_latest_snapshot(local_server) -> None:
    base_url, server = local_server
    live_log = server.record_store.directory.parent / "client.log"
    live_log.write_text(f"{LIVE_MARKER}{{}}\n", encoding="utf-8")
    server.live_log = live_log

    status, _, response = _get(base_url, "/api/live?target=panflute&seed=0")

    assert status == 200
    assert response["status"] == "error"
    assert "snapshot" in response["error"]
    list_status, _, listing = _get(base_url, "/api/explorations")
    assert list_status == 200
    assert listing == {"explorations": []}


def test_live_check_api_is_read_only_and_reports_age_for_caves(local_server, monkeypatch) -> None:
    base_url, server = local_server

    def a_write_or_plan_is_a_failure(*args, **kwargs):
        raise AssertionError("live-check must only inspect the existing log")

    monkeypatch.setattr(app, "_plan_request", a_write_or_plan_is_a_failure)
    monkeypatch.setattr(server.exploration_store, "capture", a_write_or_plan_is_a_failure)
    disabled_status, _, disabled = _get(base_url, "/api/live-check")
    assert disabled_status == 200
    assert disabled == {"check_version": 1, "status": "disabled", "log_path": None}

    log = server.record_store.directory.parent / "client check.log"
    server.live_log = log
    missing_status, _, missing = _get(base_url, "/api/live-check")
    assert missing_status == 200
    assert missing == {
        "check_version": 1,
        "status": "missing_log",
        "log_path": str(log),
    }

    log.write_text("ordinary client output\n", encoding="utf-8")
    waiting_bytes = log.read_bytes()
    waiting_status, _, waiting = _get(base_url, "/api/live-check")
    assert waiting_status == 200
    assert waiting == {
        "check_version": 1,
        "status": "waiting",
        "log_path": str(log),
    }
    assert log.read_bytes() == waiting_bytes

    _, _, demo = _get(base_url, "/api/demo")
    cave = _live_snapshot(
        demo["directions"], world_kind="cave", sequence=9, captured_at=time.time()
    )
    cave["position"].update(x=-11, y=2, z=37.5)
    _write_live_snapshot(log, cave)
    fresh_bytes = log.read_bytes()
    fresh_status, _, fresh = _get(base_url, "/api/live-check")
    assert fresh_status == 200
    assert fresh["check_version"] == 1
    assert fresh["status"] == "live"
    assert fresh["log_path"] == str(log)
    assert fresh["age_seconds"] <= 5
    assert fresh["position"] == cave["position"]
    assert fresh["world_kind"] == "cave"
    assert fresh["sequence"] == 9
    assert "world_id" not in fresh
    assert "session_id" not in fresh
    assert log.read_bytes() == fresh_bytes
    assert not server.exploration_store.directory.exists()

    stale_cave = _live_snapshot(
        demo["directions"], world_kind="cave", captured_at=time.time() - 8
    )
    _write_live_snapshot(log, stale_cave)
    stale_status, _, stale = _get(base_url, "/api/live-check")
    assert stale_status == 200
    assert stale["status"] == "stale"
    assert stale["age_seconds"] > 5
    assert stale["world_kind"] == "cave"
    assert stale["position"] == stale_cave["position"]

    future = _live_snapshot(demo["directions"], captured_at=time.time() + 10)
    _write_live_snapshot(log, future)
    future_bytes = log.read_bytes()
    future_status, _, future_result = _get(base_url, "/api/live-check")
    assert future_status == 200
    assert future_result["status"] == "error"
    assert future_result["error"] == "captured_at is ahead of the local clock."
    assert "position" not in future_result
    assert log.read_bytes() == future_bytes

    log.write_text(f"{LIVE_MARKER}{{}}\n", encoding="utf-8")
    invalid_status, _, invalid = _get(base_url, "/api/live-check")
    assert invalid_status == 200
    assert invalid["status"] == "error"
    assert "snapshot" in invalid["error"]


def test_live_check_api_distinguishes_unreadable_logs_from_missing_logs(local_server, monkeypatch) -> None:
    from dst_route_planner import connection

    base_url, server = local_server
    log = server.record_store.directory.parent / "unreadable.log"
    log.write_text("existing log", encoding="utf-8")
    server.live_log = log

    def fail_to_read(path):
        raise PermissionError("permission denied")

    monkeypatch.setattr(connection, "read_latest_snapshot", fail_to_read)
    status, _, result = _get(base_url, "/api/live-check")
    assert status == 200
    assert result == {
        "check_version": 1,
        "status": "error",
        "log_path": str(log),
        "error": "permission denied",
    }


def test_exploration_download_rejects_corrupt_and_oversize_files_without_changing_them(
    local_server, monkeypatch
) -> None:
    from dst_route_planner import exploration as exploration_module

    base_url, server = local_server
    _, _, demo = _get(base_url, "/api/demo")
    snapshot = _live_snapshot(demo["directions"])
    live_log = server.record_store.directory.parent / "client.log"
    _write_live_snapshot(live_log, snapshot)
    server.live_log = live_log
    _, _, response = _get(base_url, "/api/live?target=panflute&seed=0")
    journal_id = response["recording"]["id"]
    journal_path = server.exploration_store._journal_path(journal_id)
    original = journal_path.read_bytes()

    corrupt = original + b"not-json\n"
    journal_path.write_bytes(corrupt)
    corrupt_status, _, corrupt_response = _get(
        base_url, f"/api/explorations/{journal_id}"
    )
    assert corrupt_status == 500
    assert corrupt_response == {"error": "The exploration could not be read."}
    assert journal_path.read_bytes() == corrupt

    monkeypatch.setattr(exploration_module, "MAX_EXPLORATION_BYTES", len(corrupt) - 1)
    oversize_status, _, oversize_response = _get(
        base_url, f"/api/explorations/{journal_id}"
    )
    assert oversize_status == 500
    assert oversize_response == {"error": "The exploration could not be read."}
    assert journal_path.read_bytes() == corrupt


def test_exploration_trail_api_projects_positions_and_ignores_partial_tail(local_server) -> None:
    base_url, server = local_server
    _, _, demo = _get(base_url, "/api/demo")
    points = [(-12, 3.5), (-12, 3.5), (8.25, -20)]
    terrain_by_frame = [
        [
            {"x": 1, "z": 1, "tile": "GRASS", "passable": False},
            {"x": 4, "z": 4, "tile": "FOREST", "passable": True},
        ],
        [
            {"x": 1, "z": 1, "tile": "FOREST"},
            {"x": 2, "z": 2, "tile": "MARSH", "passable": False},
        ],
        [
            {"x": 1, "z": 1, "tile": "DECIDUOUS"},
        ],
    ]
    live_log = server.record_store.directory.parent / "client.log"
    server.live_log = live_log
    captured_times = []
    summary = None
    for sequence, (x, z) in enumerate(points, start=1):
        captured_at = time.time() - (3 - sequence) * 0.01
        captured_times.append(captured_at)
        snapshot = _live_snapshot(
            demo["directions"], sequence=sequence, captured_at=captured_at
        )
        snapshot["position"].update(x=x, z=z)
        snapshot["terrain"] = {"tile_size": 4, "tiles": terrain_by_frame[sequence - 1]}
        _write_live_snapshot(live_log, snapshot)
        live_status, _, live_response = _get(
            base_url, "/api/live?target=panflute&seed=0"
        )
        assert live_status == 200
        assert live_response["status"] == "live"
        summary = live_response["recording"]
        assert summary["frame_count"] == sequence
    other_session = _live_snapshot(
        demo["directions"], world_id="world-abc", session_id="another-session"
    )
    other_session["position"].update(x=500, z=600)
    other_session["terrain"] = {
        "tile_size": 4,
        "tiles": [{"x": 99, "z": -4, "tile": "ROCKY"}],
    }
    _write_live_snapshot(live_log, other_session)
    other_live_status, _, other_live_response = _get(
        base_url, "/api/live?target=panflute&seed=0"
    )
    assert other_live_status == 200
    other_summary = other_live_response["recording"]

    trail_status, _, trail = _get(base_url, f"/api/explorations/{summary['id']}/trail")
    assert trail_status == 200
    assert trail == {
        "trail_version": 1,
        "id": summary["id"],
        "world_id": "world-abc",
        "world_kind": "forest",
        "session_id": "session-1",
        "frame_count": 3,
        "points": [
            {"sequence": 1, "captured_at": captured_times[0], "x": -12, "z": 3.5},
            {"sequence": 2, "captured_at": captured_times[1], "x": -12, "z": 3.5},
            {"sequence": 3, "captured_at": captured_times[2], "x": 8.25, "z": -20},
        ],
        "bounds": {"min_x": -12, "max_x": 8.25, "min_z": -20, "max_z": 3.5},
        "landmarks": [
            {
                "prefab": "panflute",
                "x": 1,
                "z": 1,
                "first_seen": captured_times[0],
                "last_seen": captured_times[2],
                "first_sequence": 1,
                "last_sequence": 3,
            },
            {
                "prefab": "panflute",
                "x": 3,
                "z": 4,
                "first_seen": captured_times[0],
                "last_seen": captured_times[2],
                "first_sequence": 1,
                "last_sequence": 3,
            },
            {
                "prefab": "pigking",
                "x": 0,
                "z": 2,
                "first_seen": captured_times[0],
                "last_seen": captured_times[2],
                "first_sequence": 1,
                "last_sequence": 3,
            },
        ],
        "landmarks_truncated": False,
        "terrain": {
            "tile_size": 4,
            "tiles": [
                {
                    "x": 1,
                    "z": 1,
                    "tile": "DECIDUOUS",
                    "last_seen": captured_times[2],
                    "last_sequence": 3,
                },
                {
                    "x": 2,
                    "z": 2,
                    "tile": "MARSH",
                    "last_seen": captured_times[1],
                    "last_sequence": 2,
                    "passable": False,
                },
                {
                    "x": 4,
                    "z": 4,
                    "tile": "FOREST",
                    "last_seen": captured_times[0],
                    "last_sequence": 1,
                    "passable": True,
                },
            ],
            "truncated": False,
        },
    }
    assert trail["id"] != other_summary["id"]
    other_status, _, isolated_trail = _get(
        base_url, f"/api/explorations/{other_summary['id']}/trail"
    )
    assert other_status == 200
    assert isolated_trail["session_id"] == "another-session"
    assert isolated_trail["points"] == [
        {
            "sequence": 1,
            "captured_at": other_session["captured_at"],
            "x": 500,
            "z": 600,
        }
    ]
    assert isolated_trail["terrain"] == {
        "tile_size": 4,
        "tiles": [
            {
                "x": 99,
                "z": -4,
                "tile": "ROCKY",
                "last_seen": other_session["captured_at"],
                "last_sequence": 1,
            }
        ],
        "truncated": False,
    }
    assert isolated_trail["landmarks_truncated"] is False
    assert {item["prefab"] for item in isolated_trail["landmarks"]} == {
        "panflute",
        "pigking",
    }
    assert isolated_trail["landmarks"][0]["first_sequence"] == 1
    assert isolated_trail["landmarks"][0]["last_sequence"] == 1
    assert "private_plan_detail" not in json.dumps(trail)
    assert "directions" not in trail

    journal_path = server.exploration_store._journal_path(summary["id"])
    complete_journal = journal_path.read_bytes()
    partial_tail = b'{"replay_version":1,"snapshot":'
    journal_path.write_bytes(complete_journal + partial_tail)
    partial_status, _, partial_trail = _get(
        base_url, f"/api/explorations/{summary['id']}/trail"
    )
    assert partial_status == 200
    assert partial_trail == trail
    assert journal_path.read_bytes() == complete_journal + partial_tail

    restarted_server = app.create_server(
        port=0,
        record_dir=server.record_store.directory,
        exploration_dir=server.exploration_store.directory,
    )
    restarted_thread = threading.Thread(target=restarted_server.serve_forever, daemon=True)
    restarted_thread.start()
    host, port = restarted_server.server_address[:2]
    try:
        restarted_url = f"http://{host}:{port}"
        list_status, _, listing = _get(restarted_url, "/api/explorations")
        assert list_status == 200
        assert {item["id"] for item in listing["explorations"]} == {
            summary["id"], other_summary["id"]
        }
        restart_status, _, restarted_trail = _get(
            restarted_url, f"/api/explorations/{summary['id']}/trail"
        )
        assert restart_status == 200
        assert restarted_trail == trail
        download_status, download_headers, downloaded = _get(
            restarted_url, f"/api/explorations/{summary['id']}"
        )
        assert download_status == 200
        assert download_headers.get_content_type() == "application/x-ndjson"
        downloaded_frames = [json.loads(line) for line in downloaded.splitlines()][1:]
        downloaded_terrain = [
            frame["snapshot"]["terrain"] for frame in downloaded_frames
        ]
        assert downloaded_terrain == [
            {"tile_size": 4, "tiles": tiles} for tiles in terrain_by_frame
        ]
        assert downloaded_terrain[0]["tiles"][0]["passable"] is False
        assert "passable" not in downloaded_terrain[1]["tiles"][0]
        assert "passable" not in downloaded_terrain[2]["tiles"][0]
        isolated_status, _, restarted_isolated_trail = _get(
            restarted_url, f"/api/explorations/{other_summary['id']}/trail"
        )
        assert isolated_status == 200
        assert restarted_isolated_trail["terrain"] == isolated_trail["terrain"]
    finally:
        restarted_server.shutdown()
        restarted_server.server_close()
        restarted_thread.join(timeout=2)


def test_exploration_trail_api_handles_empty_invalid_missing_and_bad_journals(
    local_server, monkeypatch
) -> None:
    from dst_route_planner import exploration as exploration_module
    from dst_route_planner.exploration import exploration_id

    base_url, server = local_server
    invalid_status, _, invalid = _get(base_url, "/api/explorations/not-safe/trail")
    assert invalid_status == 400
    assert "64-character lowercase hexadecimal" in invalid["error"]
    missing_id = "0" * 64
    missing_status, _, missing = _get(base_url, f"/api/explorations/{missing_id}/trail")
    assert missing_status == 404
    assert missing == {"error": "Exploration not found."}

    empty_id = exploration_id("empty-world", "forest", "empty-session")
    server.exploration_store.directory.mkdir(parents=True, exist_ok=True)
    empty_path = server.exploration_store._journal_path(empty_id)
    empty_path.write_text(
        json.dumps(
            {
                "replay_version": 1,
                "id": empty_id,
                "world_id": "empty-world",
                "world_kind": "forest",
                "session_id": "empty-session",
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    empty_status, _, empty = _get(base_url, f"/api/explorations/{empty_id}/trail")
    assert empty_status == 200
    assert empty["frame_count"] == 0
    assert empty["points"] == []
    assert empty["bounds"] is None
    assert empty["landmarks"] == []
    assert empty["landmarks_truncated"] is False

    _, _, demo = _get(base_url, "/api/demo")
    snapshot = _live_snapshot(demo["directions"])
    summary = server.exploration_store.capture(snapshot, target="panflute", seed=0)
    journal_path = server.exploration_store._journal_path(summary["id"])
    original = journal_path.read_bytes()
    corrupt = original + b"not-json\n"
    journal_path.write_bytes(corrupt)
    corrupt_status, _, corrupt_response = _get(
        base_url, f"/api/explorations/{summary['id']}/trail"
    )
    assert corrupt_status == 500
    assert corrupt_response == {"error": "The exploration trail could not be read."}
    assert journal_path.read_bytes() == corrupt

    monkeypatch.setattr(exploration_module, "MAX_EXPLORATION_BYTES", len(corrupt) - 1)
    oversized_status, _, oversized_response = _get(
        base_url, f"/api/explorations/{summary['id']}/trail"
    )
    assert oversized_status == 500
    assert oversized_response == {"error": "The exploration trail could not be read."}
    assert journal_path.read_bytes() == corrupt
