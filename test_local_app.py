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
    server = app.create_server(port=0)
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
    with urlopen(base_url + path, timeout=5) as response:
        body = response.read().decode("utf-8")
        if response.headers.get_content_type() == "application/json":
            body = json.loads(body)
        return response.status, response.headers, body


def _post(base_url: str, payload: bytes | dict):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    request = Request(
        base_url + "/api/plan",
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
