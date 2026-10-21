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


def _post_import(base_url: str, payload: bytes, content_type: str = "application/x-ndjson"):
    request = Request(
        base_url + "/api/explorations/import",
        data=payload,
        headers={"Content-Type": content_type},
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


def test_only_checked_route_javascript_static_path_is_served(local_server, monkeypatch, tmp_path) -> None:
    base_url, _ = local_server
    status, headers, body = _get(base_url, "/static/checked_routes.js")

    assert status == 200
    assert headers["Content-Type"].startswith("text/javascript")
    assert headers["Cache-Control"] == "no-cache"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert body == app.CHECKED_ROUTES_JS_PATH.read_text(encoding="utf-8")
    assert "findRoute" in body

    for path in (
        "/static/app.html",
        "/static/other.js",
        "/static/checked_routes.js/extra",
    ):
        missing_status, _, missing = _get(base_url, path)
        assert missing_status == 404
        assert missing == {"error": "Route not found."}

    monkeypatch.setattr(
        app, "CHECKED_ROUTES_JS_PATH", tmp_path / "missing-checked-routes.js"
    )
    unavailable_status, _, unavailable = _get(base_url, "/static/checked_routes.js")
    assert unavailable_status == 404
    assert unavailable == {"error": "The checked-grid route script is not available."}


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


def _write_live_snapshots(path: Path, snapshots: list[dict]) -> None:
    path.write_text(
        "".join(
            f"{LIVE_MARKER}{json.dumps(snapshot, separators=(',', ':'))}\n"
            for snapshot in snapshots
        ),
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
    valid = _live_snapshot(app._demo()["directions"], sequence=1)
    live_log.write_text(
        f"{LIVE_MARKER}{json.dumps(valid, separators=(',', ':'))}\n"
        f"{LIVE_MARKER}{{}}\n",
        encoding="utf-8",
    )
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
    anchors_by_frame = [
        {"x": -12, "z": 4, "clear": True},
        None,
        {"x": 8, "z": -20, "clear": False},
    ]
    terrain_by_frame = [
        [
            {"x": 1, "z": 1, "tile": "GRASS", "passable": False},
            {"x": -12, "z": 4, "tile": "FOREST", "passable": True},
            {
                "x": 4,
                "z": 4,
                "tile": "FOREST",
                "passable": True,
                "connections": {"east": False},
            },
            {"x": 8, "z": 4, "tile": "GRASS", "passable": True},
        ],
        [
            {"x": 1, "z": 1, "tile": "FOREST"},
            {"x": 2, "z": 2, "tile": "MARSH", "passable": False},
        ],
        [
            {"x": 1, "z": 1, "tile": "DECIDUOUS"},
            {"x": 8, "z": -20, "tile": "GRASS", "passable": True},
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
        if anchors_by_frame[sequence - 1] is not None:
            snapshot["player_anchor"] = anchors_by_frame[sequence - 1]
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
            {
                "sequence": 1,
                "captured_at": captured_times[0],
                "x": -12,
                "z": 3.5,
                "player_anchor": {"x": -12, "z": 4, "clear": True},
            },
            {"sequence": 2, "captured_at": captured_times[1], "x": -12, "z": 3.5},
            {
                "sequence": 3,
                "captured_at": captured_times[2],
                "x": 8.25,
                "z": -20,
                "player_anchor": {"x": 8, "z": -20, "clear": False},
            },
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
                    "x": 8,
                    "z": -20,
                    "tile": "GRASS",
                    "last_seen": captured_times[2],
                    "last_sequence": 3,
                    "passable": True,
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
                    "x": -12,
                    "z": 4,
                    "tile": "FOREST",
                    "last_seen": captured_times[0],
                    "last_sequence": 1,
                    "passable": True,
                },
                {
                    "x": 4,
                    "z": 4,
                    "tile": "FOREST",
                    "last_seen": captured_times[0],
                    "last_sequence": 1,
                    "passable": True,
                    "connections": {"east": False},
                },
                {
                    "x": 8,
                    "z": 4,
                    "tile": "GRASS",
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
        assert downloaded_frames[0]["snapshot"]["player_anchor"] == {
            "x": -12, "z": 4, "clear": True
        }
        assert "player_anchor" not in downloaded_frames[1]["snapshot"]
        assert downloaded_frames[2]["snapshot"]["player_anchor"] == {
            "x": 8, "z": -20, "clear": False
        }
        assert downloaded_terrain == [
            {"tile_size": 4, "tiles": tiles} for tiles in terrain_by_frame
        ]
        assert downloaded_terrain[0]["tiles"][0]["passable"] is False
        assert downloaded_terrain[0]["tiles"][2]["connections"] == {"east": False}
        assert "connections" not in downloaded_terrain[1]["tiles"][0]
        assert "connections" not in downloaded_terrain[2]["tiles"][0]
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


def _replay_import_bytes(snapshot: dict) -> bytes:
    from dst_route_planner.exploration import exploration_id

    journal_id = exploration_id(
        snapshot["world_id"], snapshot["world_kind"], snapshot["session_id"]
    )
    header = {
        "replay_version": 1,
        "id": journal_id,
        "world_id": snapshot["world_id"],
        "world_kind": snapshot["world_kind"],
        "session_id": snapshot["session_id"],
    }
    frame = {
        "replay_version": 1,
        "received_at": "2026-02-01T00:00:01Z",
        "target": "panflute",
        "seed": 0,
        "snapshot": snapshot,
    }
    return b"\n".join(
        json.dumps(value, separators=(",", ":")).encode("utf-8")
        for value in (header, frame)
    )


def test_exploration_import_http_roundtrip_duplicate_conflict_and_trail(local_server) -> None:
    base_url, server = local_server
    _, _, demo = _get(base_url, "/api/demo")
    snapshot = _live_snapshot(demo["directions"])
    raw = _replay_import_bytes(snapshot)

    status, _, created = _post_import(base_url, raw, "application/x-ndjson; charset=UTF-8")

    assert status == 201
    assert created["created"] is True
    assert created["exploration"]["frame_count"] == 1
    journal_id = created["exploration"]["id"]
    download_status, _, download = _get(base_url, f"/api/explorations/{journal_id}")
    assert download_status == 200
    assert download.encode("utf-8") == raw + b"\n"
    trail_status, _, trail = _get(base_url, f"/api/explorations/{journal_id}/trail")
    assert trail_status == 200
    assert trail["frame_count"] == 1
    assert trail["points"][0]["x"] == snapshot["position"]["x"]
    assert "player_anchor" not in trail["points"][0]
    assert trail["terrain"]["tiles"] == []
    assert server.exploration_store.get_bytes(journal_id) == raw + b"\n"

    reformatted = b"\n".join(
        json.dumps(value, sort_keys=True).encode("utf-8")
        for value in (json.loads(line) for line in raw.splitlines())
    )
    duplicate_status, _, duplicate = _post_import(base_url, reformatted)
    assert duplicate_status == 200
    assert duplicate == {"exploration": created["exploration"], "created": False}
    before_conflict = server.exploration_store.get_bytes(journal_id)
    changed_frame = json.loads(raw.splitlines()[1])
    changed_frame["target"] = "pigking"
    conflict = raw.splitlines()[0] + b"\n" + json.dumps(changed_frame).encode("utf-8")
    conflict_status, _, conflict_body = _post_import(base_url, conflict)
    assert conflict_status == 409
    assert "error" in conflict_body
    assert server.exploration_store.get_bytes(journal_id) == before_conflict


def test_exploration_import_http_validation_and_size_errors(local_server) -> None:
    base_url, server = local_server
    content_status, _, content_error = _post_import(base_url, b"{}", "application/json")
    assert content_status == 400
    assert "Content-Type" in content_error["error"]

    invalid_status, _, invalid = _post_import(base_url, b"not-json")
    assert invalid_status == 400
    assert "error" in invalid
    assert not server.exploration_store.directory.exists()

    _, server = local_server
    connection = http.client.HTTPConnection(*server.server_address[:2], timeout=5)
    connection.putrequest("POST", "/api/explorations/import")
    connection.putheader("Content-Type", "application/x-ndjson")
    connection.putheader("Content-Length", str(32 * 1024 * 1024 + 1))
    connection.endheaders()
    response = connection.getresponse()
    too_large = json.loads(response.read().decode("utf-8"))
    assert response.status == 413
    assert "limit" in too_large["error"]
    connection.close()


def _track_capture_calls(monkeypatch):
    condition = threading.Condition()
    captured_keys: list[tuple[str, str, str, int]] = []
    original_capture = app.ExplorationStore.capture

    def tracked_capture(self, snapshot, **kwargs):
        summary = original_capture(self, snapshot, **kwargs)
        key = (
            snapshot["world_id"],
            snapshot["world_kind"],
            snapshot["session_id"],
            snapshot["sequence"],
        )
        with condition:
            captured_keys.append(key)
            condition.notify_all()
        return summary

    monkeypatch.setattr(app.ExplorationStore, "capture", tracked_capture)

    def wait_for_capture(snapshot: dict, count: int = 1, timeout: float = 2.0) -> None:
        key = (
            snapshot["world_id"],
            snapshot["world_kind"],
            snapshot["session_id"],
            snapshot["sequence"],
        )
        with condition:
            assert condition.wait_for(
                lambda: captured_keys.count(key) >= count, timeout=timeout
            ), f"background recorder did not process snapshot {key!r} {count} times"

    return captured_keys, wait_for_capture


def _track_live_batch_reads(monkeypatch):
    condition = threading.Condition()
    read_results: list[list[dict]] = []
    original_read = app.read_snapshot_batch

    def tracked_read(path, **kwargs):
        try:
            snapshots = original_read(path, **kwargs)
        except Exception:
            with condition:
                read_results.append([])
                condition.notify_all()
            raise
        with condition:
            read_results.append(snapshots)
            condition.notify_all()
        return snapshots

    monkeypatch.setattr(app, "read_snapshot_batch", tracked_read)

    def wait_for_result(predicate, *, after_index: int = 0, timeout: float = 2.0) -> int:
        with condition:
            assert condition.wait_for(
                lambda: any(predicate(item) for item in read_results[after_index:]),
                timeout=timeout,
            ), "background recorder did not read the expected log state"
            return len(read_results)

    return read_results, wait_for_result


def _start_background_server(tmp_path, monkeypatch, live_log, *, serve_http=False):
    monkeypatch.setattr(app, "BACKGROUND_RECORDING_INTERVAL_SECONDS", 0.02)
    server = app.create_server(
        port=0,
        record_dir=tmp_path / "records",
        exploration_dir=tmp_path / "explorations",
        live_log=live_log,
    )
    serve_thread = None
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
    if serve_http:
        serve_thread = threading.Thread(target=server.serve_forever, daemon=True)
        serve_thread.start()
    return server, serve_thread, base_url


def _close_background_server(server, serve_thread=None) -> None:
    if serve_thread is not None and serve_thread.is_alive():
        server.shutdown()
    server.server_close()
    if serve_thread is not None:
        serve_thread.join(timeout=2)


def _recorded_frame_count(server, snapshot: dict) -> int:
    summary = server.exploration_store.summary_for_snapshot(snapshot)
    if summary is None:
        return 0
    content = server.exploration_store.get_bytes(summary["id"])
    return len(content.splitlines()) - 1


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    pulse = threading.Event()
    while not predicate():
        remaining = deadline - time.monotonic()
        assert remaining > 0, "condition was not reached before timeout"
        pulse.wait(min(0.01, remaining))


def test_background_recorder_processes_batch_in_order_and_isolates_sessions(
    tmp_path, monkeypatch
) -> None:
    _, wait_for_capture = _track_capture_calls(monkeypatch)
    directions = app._demo()["directions"]
    live_log = tmp_path / "client.log"
    now = time.time()
    forest_one = _live_snapshot(directions, captured_at=now, sequence=1)
    forest_two = _live_snapshot(directions, captured_at=now + 0.01, sequence=2)
    cave = _live_snapshot(
        directions, captured_at=now + 0.02, world_kind="cave", sequence=1
    )
    another_session = _live_snapshot(
        directions,
        captured_at=now + 0.03,
        session_id="session-2",
        sequence=1,
    )
    another_world = _live_snapshot(
        directions,
        captured_at=now + 0.04,
        world_id="world-def",
        sequence=1,
    )
    _write_live_snapshots(
        live_log,
        [forest_one, forest_two, cave, another_session, another_world],
    )
    server, _, _ = _start_background_server(tmp_path, monkeypatch, live_log)

    try:
        assert server.background_recording is True
        assert server._background_recording_thread is not None
        assert server._background_recording_thread.is_alive()
        wait_for_capture(forest_one)
        wait_for_capture(forest_two)
        wait_for_capture(cave)
        wait_for_capture(another_session)
        wait_for_capture(another_world)

        assert _recorded_frame_count(server, forest_two) == 2
        assert _recorded_frame_count(server, cave) == 1
        forest_summary = server.exploration_store.summary_for_snapshot(forest_two)
        forest_frames = [
            json.loads(line)
            for line in server.exploration_store.get_bytes(forest_summary["id"])
            .splitlines()[1:]
        ]
        assert [frame["snapshot"]["sequence"] for frame in forest_frames] == [1, 2]
        summaries = server.exploration_store.list_explorations()
        assert len(summaries) == 4
        assert {item["world_kind"] for item in summaries} == {"forest", "cave"}
        assert {item["session_id"] for item in summaries} == {"session-1", "session-2"}
        assert {item["world_id"] for item in summaries} == {"world-abc", "world-def"}
    finally:
        _close_background_server(server)


def test_background_recorder_skips_waiting_errors_and_stale_then_recovers(
    tmp_path, monkeypatch
) -> None:
    reads, wait_for_result = _track_live_batch_reads(monkeypatch)
    _, wait_for_capture = _track_capture_calls(monkeypatch)
    directions = app._demo()["directions"]
    live_log = tmp_path / "client.log"
    server, _, _ = _start_background_server(tmp_path, monkeypatch, live_log)

    try:
        read_index = wait_for_result(lambda snapshots: snapshots == [])
        assert reads[read_index - 1] == []
        assert server.exploration_store.list_explorations() == []

        live_log.write_text(f"{LIVE_MARKER}{{}}\n", encoding="utf-8")
        read_index = wait_for_result(lambda snapshots: snapshots == [], after_index=read_index)
        assert server.exploration_store.list_explorations() == []

        stale = _live_snapshot(
            directions, sequence=1, captured_at=time.time() - 10
        )
        _write_live_snapshot(live_log, stale)
        read_index = wait_for_result(
            lambda snapshots: any(
                snapshot.get("captured_at") == stale["captured_at"]
                for snapshot in snapshots
            ),
            after_index=read_index,
        )
        assert _recorded_frame_count(server, stale) == 0
        assert server.exploration_store.list_explorations() == []

        fresh = _live_snapshot(directions, sequence=1)
        _write_live_snapshot(live_log, fresh)
        wait_for_capture(fresh)
        assert _recorded_frame_count(server, fresh) == 1

        recovered = _live_snapshot(directions, sequence=2)
        _write_live_snapshot(live_log, recovered)
        wait_for_capture(recovered)
        assert _recorded_frame_count(server, recovered) == 2
    finally:
        _close_background_server(server)


def test_background_recorder_skips_stale_future_and_unsupported_then_recovers(
    tmp_path, monkeypatch
) -> None:
    _, wait_for_capture = _track_capture_calls(monkeypatch)
    directions = app._demo()["directions"]
    live_log = tmp_path / "client.log"
    server, _, _ = _start_background_server(tmp_path, monkeypatch, live_log)

    try:
        stale = _live_snapshot(
            directions, captured_at=time.time() - 10, sequence=1
        )
        _write_live_snapshot(live_log, stale)
        _wait_until(lambda: server.exploration_store.list_explorations() == [])

        future = _live_snapshot(
            directions, captured_at=time.time() + 10, sequence=2
        )
        unsupported = _live_snapshot(
            directions, world_kind="ocean", sequence=3
        )
        fresh = _live_snapshot(directions, sequence=4)
        _write_live_snapshots(live_log, [stale, future, unsupported, fresh])
        wait_for_capture(fresh)

        summary = server.exploration_store.summary_for_snapshot(fresh)
        frames = [
            json.loads(line)
            for line in server.exploration_store.get_bytes(summary["id"]).splitlines()[1:]
        ]
        assert [frame["snapshot"]["sequence"] for frame in frames] == [4]
    finally:
        _close_background_server(server)


def test_background_recorder_skips_bad_rows_and_completes_partial_tail(
    tmp_path, monkeypatch
) -> None:
    captured_keys, wait_for_capture = _track_capture_calls(monkeypatch)
    directions = app._demo()["directions"]
    live_log = tmp_path / "client.log"
    first = _live_snapshot(directions, sequence=1)
    second = _live_snapshot(directions, sequence=2)
    first_line = (
        f"{LIVE_MARKER}{json.dumps(first, separators=(',', ':'))}\n"
    ).encode("utf-8")
    second_line = f"{LIVE_MARKER}{json.dumps(second, separators=(',', ':'))}".encode(
        "utf-8"
    )
    live_log.write_bytes(
        b"ordinary client output\n"
        + f"{LIVE_MARKER}{{broken json}}\n".encode("ascii")
        + first_line
        + second_line[: len(second_line) // 2]
    )
    server, _, _ = _start_background_server(tmp_path, monkeypatch, live_log)

    try:
        wait_for_capture(first)
        second_key = ("world-abc", "forest", "session-1", 2)
        assert second_key not in captured_keys

        with live_log.open("ab") as log_file:
            log_file.write(second_line[len(second_line) // 2 :] + b"\n")
        wait_for_capture(second)

        summary = server.exploration_store.summary_for_snapshot(second)
        frames = [
            json.loads(line)
            for line in server.exploration_store.get_bytes(summary["id"]).splitlines()[1:]
        ]
        assert [frame["snapshot"]["sequence"] for frame in frames] == [1, 2]
        assert captured_keys.count(second_key) == 1
    finally:
        _close_background_server(server)


def test_live_get_updates_background_query_only_after_valid_parameters(
    tmp_path, monkeypatch
) -> None:
    _, wait_for_capture = _track_capture_calls(monkeypatch)
    directions = app._demo()["directions"]
    live_log = tmp_path / "client.log"
    initial = _live_snapshot(directions, sequence=1)
    _write_live_snapshot(live_log, initial)
    server, serve_thread, base_url = _start_background_server(
        tmp_path, monkeypatch, live_log, serve_http=True
    )

    try:
        wait_for_capture(initial)
        status, _, live_result = _get(
            base_url, "/api/live?target=pigking&seed=17"
        )
        assert status == 200
        assert live_result["status"] == "live"

        invalid_status, _, invalid = _get(
            base_url, "/api/live?target=unknown&seed=99"
        )
        assert invalid_status == 400
        assert "unknown target" in invalid["error"]

        options_status, _, options = _get(base_url, "/api/options")
        assert options_status == 200
        assert options["background_recording"] is True
        assert set(options) == {
            "targets",
            "tile_types",
            "prefabs",
            "directions",
            "background_recording",
        }

        updated = _live_snapshot(directions, sequence=2)
        _write_live_snapshot(live_log, updated)
        wait_for_capture(updated)
        summary = server.exploration_store.summary_for_snapshot(updated)
        frames = [
            json.loads(line)
            for line in server.exploration_store.get_bytes(summary["id"]).splitlines()[1:]
        ]
        assert [(frame["target"], frame["seed"]) for frame in frames] == [
            ("panflute", 0),
            ("pigking", 17),
        ]
    finally:
        _close_background_server(server, serve_thread)


def test_live_get_before_background_batch_cannot_skip_intermediate_frames(
    tmp_path, monkeypatch
) -> None:
    captured_keys, wait_for_capture = _track_capture_calls(monkeypatch)
    directions = app._demo()["directions"]
    live_log = tmp_path / "client.log"
    snapshots = [_live_snapshot(directions, sequence=sequence) for sequence in (1, 2, 3)]
    _write_live_snapshots(live_log, snapshots)

    batch_read_entered = threading.Event()
    release_batch_read = threading.Event()
    read_count = 0
    original_batch_read = app.read_snapshot_batch

    def delayed_batch_read(path, **kwargs):
        nonlocal read_count
        read_count += 1
        if read_count == 1:
            batch_read_entered.set()
            assert release_batch_read.wait(timeout=3)
        return original_batch_read(path, **kwargs)

    monkeypatch.setattr(app, "read_snapshot_batch", delayed_batch_read)
    original_plan = app._plan_request
    plan_count = 0

    def counted_plan(*args, **kwargs):
        nonlocal plan_count
        plan_count += 1
        return original_plan(*args, **kwargs)

    monkeypatch.setattr(app, "_plan_request", counted_plan)
    server, serve_thread, base_url = _start_background_server(
        tmp_path, monkeypatch, live_log, serve_http=True
    )

    try:
        assert batch_read_entered.wait(timeout=2)
        first_status, _, first_result = _get(
            base_url, "/api/live?target=panflute&seed=0"
        )
        assert first_status == 200
        assert first_result["snapshot"] == snapshots[-1]
        assert "recording" not in first_result
        assert server.exploration_store.list_explorations() == []

        for _ in range(2):
            status, _, result = _get(base_url, "/api/live?target=panflute&seed=0")
            assert status == 200
            assert result["snapshot"] == snapshots[-1]
        assert plan_count == 1
        assert server.exploration_store.list_explorations() == []

        release_batch_read.set()
        for snapshot in snapshots:
            wait_for_capture(snapshot)
        summary = server.exploration_store.summary_for_snapshot(snapshots[-1])
        frames = [
            json.loads(line)
            for line in server.exploration_store.get_bytes(summary["id"]).splitlines()[1:]
        ]
        assert [frame["snapshot"]["sequence"] for frame in frames] == [1, 2, 3]
        assert captured_keys.count(
            ("world-abc", "forest", "session-1", 1)
        ) == 1
        _wait_until(lambda: read_count >= 3)
        assert plan_count == 3
        assert len(captured_keys) == 3
    finally:
        release_batch_read.set()
        _close_background_server(server, serve_thread)


def test_background_write_failure_stays_visible_and_retries_without_replanning(
    tmp_path, monkeypatch
) -> None:
    captured_keys, wait_for_capture = _track_capture_calls(monkeypatch)
    directions = app._demo()["directions"]
    first = _live_snapshot(directions, sequence=1)
    failed = _live_snapshot(directions, sequence=2)
    later = _live_snapshot(directions, sequence=3)
    live_log = tmp_path / "client.log"
    _write_live_snapshots(live_log, [first, failed])
    original_capture = app.ExplorationStore.capture
    retry_entered = threading.Event()
    release_retry = threading.Event()
    failed_sequence_attempts = 0

    def fail_once_then_pause_retry(self, captured_snapshot, **kwargs):
        nonlocal failed_sequence_attempts
        if captured_snapshot["sequence"] == 2:
            failed_sequence_attempts += 1
            if failed_sequence_attempts == 1:
                raise OSError("disk full")
            if failed_sequence_attempts == 2:
                retry_entered.set()
                assert release_retry.wait(timeout=3)
        return original_capture(self, captured_snapshot, **kwargs)

    monkeypatch.setattr(app.ExplorationStore, "capture", fail_once_then_pause_retry)
    original_plan = app._plan_request
    plan_count = 0

    def counted_plan(*args, **kwargs):
        nonlocal plan_count
        plan_count += 1
        return original_plan(*args, **kwargs)

    monkeypatch.setattr(app, "_plan_request", counted_plan)
    server, serve_thread, base_url = _start_background_server(
        tmp_path, monkeypatch, live_log, serve_http=True
    )

    try:
        wait_for_capture(first)
        assert retry_entered.wait(timeout=2)
        _write_live_snapshots(live_log, [first, failed, later])
        status, _, result = _get(base_url, "/api/live?target=panflute&seed=0")
        assert status == 200
        assert result["snapshot"] == later
        assert result["recording"] == {"status": "error", "error": "disk full"}
        assert plan_count == 3
        assert _recorded_frame_count(server, first) == 1
        assert ("world-abc", "forest", "session-1", 3) not in captured_keys

        release_retry.set()
        wait_for_capture(failed)
        wait_for_capture(later)
        summary = server.exploration_store.summary_for_snapshot(later)
        frames = [
            json.loads(line)
            for line in server.exploration_store.get_bytes(summary["id"]).splitlines()[1:]
        ]
        assert [frame["snapshot"]["sequence"] for frame in frames] == [1, 2, 3]
        assert plan_count == 3
    finally:
        release_retry.set()
        _close_background_server(server, serve_thread)


def test_background_recorder_stops_on_server_close(tmp_path, monkeypatch) -> None:
    captured_keys, wait_for_capture = _track_capture_calls(monkeypatch)
    directions = app._demo()["directions"]
    live_log = tmp_path / "client.log"
    snapshots = [_live_snapshot(directions, sequence=n) for n in range(1, 5)]
    for snapshot in snapshots:
        snapshot["current"]["note"] = f"sequence-{snapshot['sequence']}"
    _write_live_snapshots(live_log, snapshots)
    plan_entered = threading.Event()
    release_plan = threading.Event()
    original_plan = app._plan_request

    def pause_second_plan(payload, kb=app.KB):
        if payload["current"]["note"] == "sequence-2":
            plan_entered.set()
            assert release_plan.wait(timeout=3)
        return original_plan(payload, kb)

    monkeypatch.setattr(app, "_plan_request", pause_second_plan)
    server, _, _ = _start_background_server(tmp_path, monkeypatch, live_log)

    wait_for_capture(snapshots[0])
    assert plan_entered.wait(timeout=2)
    recorder_thread = server._background_recording_thread
    assert recorder_thread is not None and recorder_thread.is_alive()
    close_thread = threading.Thread(target=server.server_close, daemon=True)
    close_thread.start()
    assert server._background_recording_stop.wait(timeout=1)
    release_plan.set()
    close_thread.join(timeout=2)
    assert not close_thread.is_alive()
    recorder_thread.join(timeout=0.2)
    assert not recorder_thread.is_alive()
    assert captured_keys == [("world-abc", "forest", "session-1", 1)]
    assert _recorded_frame_count(server, snapshots[0]) == 1


def test_background_recording_is_disabled_for_missing_log_or_explicit_opt_out(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(app, "BACKGROUND_RECORDING_INTERVAL_SECONDS", 0.02)
    directions = app._demo()["directions"]

    no_initial_log = app.create_server(
        port=0,
        record_dir=tmp_path / "records-no-log",
        exploration_dir=tmp_path / "explorations-no-log",
    )
    late_log = tmp_path / "late-client.log"
    _write_live_snapshot(late_log, _live_snapshot(directions))
    no_initial_log.live_log = late_log
    try:
        assert no_initial_log.background_recording is False
        assert no_initial_log._background_recording_thread is None
        assert no_initial_log.exploration_store.list_explorations() == []
    finally:
        no_initial_log.server_close()

    opted_out_log = tmp_path / "opted-out-client.log"
    _write_live_snapshot(opted_out_log, _live_snapshot(directions))
    opted_out = app.create_server(
        port=0,
        record_dir=tmp_path / "records-opted-out",
        exploration_dir=tmp_path / "explorations-opted-out",
        live_log=opted_out_log,
        background_recording=False,
    )
    try:
        assert opted_out.background_recording is False
        assert opted_out._background_recording_thread is None
        assert opted_out.exploration_store.list_explorations() == []
    finally:
        opted_out.server_close()


def test_run_app_closes_background_recorder_when_browser_open_fails(
    tmp_path, monkeypatch
) -> None:
    directions = app._demo()["directions"]
    live_log = tmp_path / "client.log"
    snapshot = _live_snapshot(directions, sequence=1)
    _write_live_snapshot(live_log, snapshot)
    monkeypatch.setattr(app, "BACKGROUND_RECORDING_INTERVAL_SECONDS", 0.02)
    server_holder = []

    original_create_server = app.create_server

    def create_test_server(*args, **kwargs):
        server = original_create_server(
            *args,
            record_dir=tmp_path / "records",
            exploration_dir=tmp_path / "explorations",
            **kwargs,
        )
        server_holder.append(server)
        return server

    def fail_to_open(*args, **kwargs):
        raise RuntimeError("browser open failed")

    monkeypatch.setattr(app, "create_server", create_test_server)
    monkeypatch.setattr(app.webbrowser, "open", fail_to_open)

    with pytest.raises(RuntimeError, match="browser open failed"):
        app.run_app(port=0, open_browser=True, live_log=live_log)

    server = server_holder[0]
    recorder_thread = server._background_recording_thread
    assert recorder_thread is not None
    assert not recorder_thread.is_alive()
