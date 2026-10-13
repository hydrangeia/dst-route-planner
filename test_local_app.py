from __future__ import annotations

import copy
import http.client
import json
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from dst_route_planner import app


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
