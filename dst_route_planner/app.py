from __future__ import annotations

import json
import logging
import mimetypes
import webbrowser
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from dst_route_planner.inference import initial_belief, top_items, update_belief
from dst_route_planner.io import InputValidationError, direction_observations_from_dict, observation_from_dict
from dst_route_planner.knowledge import build_forest_default_kb
from dst_route_planner.models import Direction
from dst_route_planner.navigation import probabilities_by_direction, rank_directions


MAX_REQUEST_BYTES = 256 * 1024
KB = build_forest_default_kb()
PACKAGE_DIR = Path(__file__).resolve().parent
APP_HTML_PATH = PACKAGE_DIR / "static" / "app.html"
DEMO_JSON_PATH = PACKAGE_DIR.parent / "examples" / "panflute_observation.json"
_LOG = logging.getLogger(__name__)


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InputValidationError(f"{label} must be a JSON object.")
    return value


def _plan_request(payload: Any, kb=KB) -> dict[str, Any]:
    data = _require_mapping(payload, "request")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise InputValidationError("request must use schema_version 1.")

    allowed_fields = {"schema_version", "target", "seed", "directions", "current"}
    extra_fields = set(data) - allowed_fields
    if extra_fields:
        names = ", ".join(sorted(str(field) for field in extra_fields))
        raise InputValidationError(f"request has unsupported field(s): {names}.")

    target = data.get("target")
    if not isinstance(target, str) or not target.strip():
        raise InputValidationError("target must be a non-empty prefab ID.")
    if target not in kb.target_chains:
        raise InputValidationError(f"unknown target {target!r}; choose a target from /api/options.")

    seed = data.get("seed")
    if type(seed) is not int:
        raise InputValidationError("seed must be an integer.")

    raw_directions = _require_mapping(data.get("directions"), "directions")
    observations = direction_observations_from_dict(
        {"schema_version": 1, "directions": raw_directions}
    )

    belief = initial_belief(kb)
    current = data.get("current")
    if current is not None:
        belief = update_belief(kb, belief, observation_from_dict(_require_mapping(current, "current")))

    scores = rank_directions(kb, target, belief, observations, seed=seed)
    probabilities = probabilities_by_direction(scores)
    ranked_directions = [
        {
            "direction": score.direction.value,
            "score": score.score,
            "p_dir": probabilities.get(score.direction.value, 0.0),
            "p_task": score.target_task_probability,
            "p_room": score.target_room_probability,
            "explanation": list(score.explanation),
        }
        for score in scores
    ]

    return {
        "target": target,
        "seed": seed,
        "directions": ranked_directions,
        "current_tasks": [
            {"name": name, "probability": probability}
            for name, probability in top_items(dict(belief.task_probs), 5)
        ],
    }


def _options(kb=KB) -> dict[str, list[str]]:
    tile_types = {room.tile for room in kb.rooms.values()}
    prefabs: set[str] = set()
    for room in kb.rooms.values():
        prefabs.update(room.required_prefabs)
        prefabs.update(room.countprefabs)
        prefabs.update(room.distributeprefabs)
        prefabs.update(room.negative_prefabs)
        prefabs.update(room.prefab_exclusions)
        prefabs.update(room.prefab_weights)
    for layout in kb.static_layouts.values():
        prefabs.update(layout.prefabs)
    for chains in kb.target_chains.values():
        for chain in chains:
            prefabs.add(chain.target_prefab)
            prefabs.update(chain.landmark_prefabs)

    return {
        "targets": sorted(kb.target_chains),
        "tile_types": sorted(tile_types),
        "prefabs": sorted(prefabs),
        "directions": [
            direction.value for direction in Direction if direction is not Direction.UNKNOWN
        ],
    }


def _demo(kb=KB) -> dict[str, Any]:
    try:
        example = json.loads(DEMO_JSON_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("The packaged Pan Flute example could not be loaded.") from exc
    if not isinstance(example, dict) or not isinstance(example.get("directions"), dict):
        raise RuntimeError("The packaged Pan Flute example has an invalid shape.")
    # Validate it through the same manual-input parser used by POST /api/plan.
    direction_observations_from_dict({"schema_version": 1, "directions": example["directions"]})
    return {
        "schema_version": 1,
        "target": "panflute",
        "seed": 0,
        "directions": example["directions"],
    }


def _json_object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputValidationError(f"request contains duplicate JSON key {key!r}.")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise InputValidationError(f"request contains invalid JSON value {value}.")


class _PlannerHandler(BaseHTTPRequestHandler):
    server_version = "DSTRoutePlanner/1"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlsplit(self.path).path
        if path == "/api/options":
            self._send_json(200, _options(self.server.kb))
            return
        if path == "/api/demo":
            try:
                self._send_json(200, _demo(self.server.kb))
            except RuntimeError:
                _LOG.exception("Unable to load the bundled example input")
                self._send_json(500, {"error": "The bundled demo could not be loaded."})
            return
        if path == "/":
            self._send_app_html()
            return
        self._send_json(404, {"error": "Route not found."})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlsplit(self.path).path
        if path != "/api/plan":
            self._send_json(404, {"error": "Route not found."})
            return

        try:
            payload = self._read_json_body()
            response = _plan_request(payload, self.server.kb)
        except _ResponseAlreadySent:
            return
        except InputValidationError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except Exception:
            _LOG.exception("Planner request failed")
            self._send_json(500, {"error": "The planner could not process this request."})
            return
        self._send_json(200, response)

    def _read_json_body(self) -> Any:
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise InputValidationError("Content-Type must be application/json.")

        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise InputValidationError("Content-Length is required.")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise InputValidationError("Content-Length must be a non-negative integer.") from exc
        if length < 0:
            raise InputValidationError("Content-Length must be a non-negative integer.")
        if length > MAX_REQUEST_BYTES:
            self._send_json(413, {"error": f"Request body exceeds the {MAX_REQUEST_BYTES}-byte limit."})
            raise _ResponseAlreadySent

        body = self.rfile.read(length)
        if len(body) != length:
            raise InputValidationError("Request body ended before Content-Length bytes were received.")
        try:
            text = body.decode("utf-8")
            return json.loads(
                text,
                object_pairs_hook=_json_object_no_duplicates,
                parse_constant=_reject_json_constant,
            )
        except UnicodeDecodeError as exc:
            raise InputValidationError("Request body must be UTF-8 JSON.") from exc
        except json.JSONDecodeError as exc:
            raise InputValidationError(f"invalid JSON: {exc.msg}") from exc

    def _send_json(self, status: int, payload: Mapping[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_app_html(self) -> None:
        try:
            content = APP_HTML_PATH.read_bytes()
        except OSError:
            self._send_json(404, {"error": "The local app page is not available."})
            return
        mime_type, _ = mimetypes.guess_type(APP_HTML_PATH.name)
        self.send_response(200)
        self.send_header("Content-Type", f"{mime_type or 'text/html'}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        _LOG.info("%s - %s", self.address_string(), format % args)


class _ResponseAlreadySent(Exception):
    pass


def create_server(port: int = 0) -> ThreadingHTTPServer:
    """Create a local-only HTTP server; port 0 asks the OS for a free port."""
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("port must be an integer from 0 through 65535.")

    class PlannerHTTPServer(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

        def __init__(self, address):
            super().__init__(address, _PlannerHandler)
            self.kb = KB

    return PlannerHTTPServer(("127.0.0.1", port))


def run_app(port: int = 8765, open_browser: bool = True) -> None:
    """Run the local planner app until interrupted with Ctrl+C."""
    server = create_server(port)
    address, actual_port = server.server_address[:2]
    url = f"http://{address}:{actual_port}/"
    print(f"DST Route Planner is available at {url}")
    if open_browser:
        webbrowser.open(url, new=2)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
