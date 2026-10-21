from __future__ import annotations

import json
import logging
import mimetypes
import threading
import time
import webbrowser
from collections import OrderedDict
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from dst_route_planner.inference import initial_belief, top_items, update_belief
from dst_route_planner.io import InputValidationError, direction_observations_from_dict, observation_from_dict
from dst_route_planner.knowledge import build_forest_default_kb
from dst_route_planner.connection import inspect_live_log
from dst_route_planner.live import (
    FRESHNESS_SECONDS,
    LiveSnapshotError,
    freshness_status,
    nearest_visible_target,
    read_latest_snapshot,
    read_snapshot_batch,
)
from dst_route_planner.exploration import (
    MAX_EXPLORATION_BYTES,
    CorruptExplorationError,
    ExplorationConflictError,
    ExplorationNotFoundError,
    ExplorationStore,
    ExplorationTooLargeError,
    InvalidExplorationIdError,
)
from dst_route_planner.models import Direction
from dst_route_planner.navigation import probabilities_by_direction, rank_directions
from dst_route_planner.records import (
    CorruptRecordError,
    InvalidRecordIdError,
    RecordNotFoundError,
    RecordStore,
)
from dst_route_planner.trail import TrailDataError, project_trail


MAX_REQUEST_BYTES = 256 * 1024
BACKGROUND_RECORDING_INTERVAL_SECONDS = 1.0
BACKGROUND_RECORDING_JOIN_TIMEOUT_SECONDS = 2.0
KB = build_forest_default_kb()
PACKAGE_DIR = Path(__file__).resolve().parent
APP_HTML_PATH = PACKAGE_DIR / "static" / "app.html"
CHECKED_ROUTES_JS_PATH = PACKAGE_DIR / "static" / "checked_routes.js"
DEMO_JSON_PATH = PACKAGE_DIR.parent / "examples" / "panflute_observation.json"
DEFAULT_RECORD_DIR = PACKAGE_DIR.parent / ".dst-route-planner" / "records"
_LOG = logging.getLogger(__name__)
BACKGROUND_PLAN_CACHE_SIZE = 512
BACKGROUND_RECORDED_SEQUENCE_CACHE_SIZE = 2048


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InputValidationError(f"{label} must be a JSON object.")
    return value


def _validated_observation_request(payload: Any, kb=KB) -> tuple[
    dict[str, Any], str, int, list[Any], Any | None
]:
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

    current = data.get("current")
    parsed_current = None
    if current is not None:
        parsed_current = observation_from_dict(_require_mapping(current, "current"))
    return dict(data), target, seed, observations, parsed_current


def _plan_request(payload: Any, kb=KB) -> dict[str, Any]:
    _, target, seed, observations, current_observation = _validated_observation_request(payload, kb)
    belief = initial_belief(kb)
    if current_observation is not None:
        belief = update_belief(kb, belief, current_observation)

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


def _parse_live_query(query: str, kb=KB) -> tuple[str, int]:
    parameters = parse_qs(query, keep_blank_values=True)
    unsupported = set(parameters) - {"target", "seed"}
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise InputValidationError(f"unsupported query parameter(s): {names}.")
    for key in ("target", "seed"):
        if len(parameters.get(key, [])) > 1:
            raise InputValidationError(f"{key} must be supplied at most once.")

    target = parameters.get("target", ["panflute"])[0]
    if not target.strip():
        raise InputValidationError("target must be a non-empty prefab ID.")
    if target not in kb.target_chains:
        raise InputValidationError(f"unknown target {target!r}; choose a target from /api/options.")
    raw_seed = parameters.get("seed", ["0"])[0]
    try:
        seed = int(raw_seed)
    except ValueError as exc:
        raise InputValidationError("seed must be an integer.") from exc
    return target, seed


def _live_request(
    query: str,
    live_log: Path | None,
    kb=KB,
    exploration_store: ExplorationStore | None = None,
    *,
    parsed_query: tuple[str, int] | None = None,
    capture_recording: bool = True,
    plan_cache: OrderedDict | None = None,
    plan_cache_lock: threading.Lock | None = None,
) -> dict[str, Any]:
    target, seed = parsed_query or _parse_live_query(query, kb)

    if live_log is None:
        return {"status": "disabled"}
    try:
        snapshot = read_latest_snapshot(live_log)
    except (LiveSnapshotError, OSError) as exc:
        return {"status": "error", "error": str(exc)}
    if snapshot is None:
        return {"status": "waiting"}

    return _live_snapshot_request(
        snapshot,
        target,
        seed,
        kb,
        exploration_store,
        capture_recording=capture_recording,
        plan_cache=plan_cache,
        plan_cache_lock=plan_cache_lock,
    )


def _snapshot_identity(snapshot: Mapping[str, Any]) -> tuple[str, str, str, int]:
    return (
        snapshot["world_id"],
        snapshot["world_kind"],
        snapshot["session_id"],
        snapshot["sequence"],
    )


def _recording_identity(snapshot: Mapping[str, Any]) -> tuple[str, str, str]:
    return (snapshot["world_id"], snapshot["world_kind"], snapshot["session_id"])


def _cached_plan(
    snapshot: Mapping[str, Any],
    target: str,
    seed: int,
    kb,
    cache: OrderedDict | None,
    cache_lock: threading.Lock | None,
) -> tuple[dict[str, Any] | None, str | None]:
    request = {
        "schema_version": 1,
        "target": target,
        "seed": seed,
        "current": snapshot["current"],
        "directions": snapshot["directions"],
    }
    if cache is None or cache_lock is None:
        return _plan_request(request, kb), None

    key = (*_snapshot_identity(snapshot), target, seed)
    with cache_lock:
        if key in cache:
            cache.move_to_end(key)
            return cache[key]
        try:
            outcome = (_plan_request(request, kb), None)
        except Exception as exc:
            _LOG.exception("Unable to plan from a live snapshot")
            return None, str(exc)
        cache[key] = outcome
        while len(cache) > BACKGROUND_PLAN_CACHE_SIZE:
            cache.popitem(last=False)
        return outcome


def _live_snapshot_request(
    snapshot: dict[str, Any],
    target: str,
    seed: int,
    kb,
    exploration_store: ExplorationStore | None = None,
    *,
    capture_recording: bool = True,
    plan_cache: OrderedDict | None = None,
    plan_cache_lock: threading.Lock | None = None,
    stop_event: threading.Event | None = None,
) -> dict[str, Any]:
    """Build the live response for one already validated snapshot."""

    now = time.time()
    try:
        status, age = freshness_status(snapshot, now=now)
    except LiveSnapshotError as exc:
        return {"status": "error", "error": str(exc)}
    result: dict[str, Any] = {
        "status": status,
        "age_seconds": age,
        "snapshot": snapshot,
    }
    if age > FRESHNESS_SECONDS:
        if exploration_store is not None and snapshot["world_kind"] in {"forest", "cave"}:
            try:
                summary = exploration_store.summary_for_snapshot(snapshot)
                if summary is not None:
                    result["recording"] = summary
            except Exception as exc:
                _LOG.exception("Unable to read the matching live exploration journal")
                result["recording"] = {"status": "error", "error": str(exc)}
        return result
    if status not in {"live", "unsupported_world"}:
        return result

    if status == "live":
        try:
            plan, plan_error = _cached_plan(
                snapshot, target, seed, kb, plan_cache, plan_cache_lock
            )
            if plan_error is not None:
                return {
                    "status": "error",
                    "age_seconds": age,
                    "snapshot": snapshot,
                    "error": plan_error,
                }
            result["plan"] = plan
            visible_target = nearest_visible_target(snapshot, target)
            if visible_target is not None:
                result["visible_target"] = visible_target
        except Exception as exc:
            _LOG.exception("Unable to plan from the latest live snapshot")
            return {
                "status": "error",
                "age_seconds": age,
                "snapshot": snapshot,
                "error": str(exc),
            }

    # Caves do not have forest inference yet, but fresh cave snapshots are
    # still useful as an exploration replay.
    if (
        exploration_store is not None
        and age <= FRESHNESS_SECONDS
        and snapshot["world_kind"] in {"forest", "cave"}
    ):
        if stop_event is not None and stop_event.is_set():
            return result
        try:
            if capture_recording:
                result["recording"] = exploration_store.capture(
                    snapshot,
                    target=target,
                    seed=seed,
                    plan=result.get("plan"),
                )
            else:
                summary = exploration_store.summary_for_snapshot(snapshot)
                if summary is not None:
                    result["recording"] = summary
        except Exception as exc:
            # A failed local write must not interrupt the position or plan API.
            _LOG.exception("Unable to record the latest live snapshot")
            result["recording"] = {"status": "error", "error": str(exc)}
    return result


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
            self._send_json(
                200,
                {
                    **_options(self.server.kb),
                    "background_recording": self.server.background_recording,
                },
            )
            return
        if path == "/api/demo":
            try:
                self._send_json(200, _demo(self.server.kb))
            except RuntimeError:
                _LOG.exception("Unable to load the bundled example input")
                self._send_json(500, {"error": "The bundled demo could not be loaded."})
            return
        if path == "/api/live":
            query = urlsplit(self.path).query
            try:
                target, seed = _parse_live_query(query, self.server.kb)
            except InputValidationError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            self.server.update_background_query(target, seed)
            try:
                result = _live_request(
                    query,
                    self.server.live_log,
                    self.server.kb,
                    self.server.exploration_store,
                    parsed_query=(target, seed),
                    capture_recording=not self.server.background_recording,
                    plan_cache=self.server._live_plan_cache,
                    plan_cache_lock=self.server._live_plan_cache_lock,
                )
            except InputValidationError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            if self.server.background_recording and "snapshot" in result:
                recording_error = self.server.background_recording_error(
                    result["snapshot"]
                )
                if recording_error is not None:
                    result["recording"] = {
                        "status": "error",
                        "error": recording_error,
                    }
            self._send_json(200, result)
            return
        if path == "/api/live-check":
            self._send_json(200, inspect_live_log(self.server.live_log))
            return
        if path == "/api/explorations":
            try:
                explorations = self.server.exploration_store.list_explorations()
            except OSError:
                _LOG.exception("Unable to list live exploration replays")
                self._send_json(500, {"error": "Explorations could not be listed."})
                return
            self._send_json(200, {"explorations": explorations})
            return
        trail_prefix = "/api/explorations/"
        trail_suffix = "/trail"
        if path.startswith(trail_prefix) and path.endswith(trail_suffix):
            exploration_id = path[len(trail_prefix) : -len(trail_suffix)]
            if not exploration_id:
                self._send_json(404, {"error": "Route not found."})
                return
            try:
                normalized_id = self.server.exploration_store.normalize_id(exploration_id)
                content = self.server.exploration_store.get_bytes(normalized_id)
                trail = project_trail(content)
            except InvalidExplorationIdError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except ExplorationNotFoundError:
                self._send_json(404, {"error": "Exploration not found."})
                return
            except (CorruptExplorationError, TrailDataError):
                self._send_json(500, {"error": "The exploration trail could not be read."})
                return
            except OSError:
                _LOG.exception("Unable to read live exploration trail")
                self._send_json(500, {"error": "The exploration trail could not be read."})
                return
            self._send_json(200, trail)
            return
        if path.startswith("/api/explorations/"):
            exploration_id = path.removeprefix("/api/explorations/")
            if not exploration_id or "/" in exploration_id:
                self._send_json(404, {"error": "Route not found."})
                return
            try:
                normalized_id = self.server.exploration_store.normalize_id(exploration_id)
                content = self.server.exploration_store.get_bytes(normalized_id)
            except InvalidExplorationIdError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except ExplorationNotFoundError:
                self._send_json(404, {"error": "Exploration not found."})
                return
            except CorruptExplorationError:
                self._send_json(500, {"error": "The exploration could not be read."})
                return
            except OSError:
                _LOG.exception("Unable to read live exploration replay")
                self._send_json(500, {"error": "The exploration could not be read."})
                return
            self._send_exploration_download(normalized_id, content)
            return
        if path == "/api/records":
            try:
                records = self.server.record_store.list_records(
                    observation_validator=lambda observation: _validated_observation_request(
                        observation, self.server.kb
                    )
                )
            except OSError:
                _LOG.exception("Unable to list saved exploration records")
                self._send_json(500, {"error": "Saved records could not be listed."})
                return
            self._send_json(200, {"records": records})
            return
        if path.startswith("/api/records/"):
            record_id = path.removeprefix("/api/records/")
            if not record_id or "/" in record_id:
                self._send_json(404, {"error": "Route not found."})
                return
            try:
                record = self.server.record_store.get(record_id)
                _validated_observation_request(record["observation"], self.server.kb)
            except InvalidRecordIdError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except RecordNotFoundError:
                self._send_json(404, {"error": "Saved record not found."})
                return
            except (CorruptRecordError, InputValidationError):
                self._send_json(500, {"error": "The saved record could not be read."})
                return
            except OSError:
                _LOG.exception("Unable to read saved exploration record")
                self._send_json(500, {"error": "The saved record could not be read."})
                return
            self._send_json(200, record)
            return
        if path == "/static/checked_routes.js":
            self._send_checked_routes_js()
            return
        if path == "/":
            self._send_app_html()
            return
        self._send_json(404, {"error": "Route not found."})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlsplit(self.path).path
        if path == "/api/explorations/import":
            try:
                raw = self._read_exploration_body()
                summary, created = self.server.exploration_store.import_bytes(raw)
            except _ResponseAlreadySent:
                return
            except InputValidationError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except ExplorationTooLargeError as exc:
                self._send_json(413, {"error": str(exc)})
                return
            except CorruptExplorationError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            except ExplorationConflictError as exc:
                self._send_json(409, {"error": str(exc)})
                return
            except OSError:
                _LOG.exception("Unable to import exploration replay")
                self._send_json(500, {"error": "The exploration could not be imported."})
                return
            except Exception:
                _LOG.exception("Exploration import failed")
                self._send_json(500, {"error": "The exploration could not be imported."})
                return
            self._send_json(201 if created else 200, {"exploration": summary, "created": created})
            return

        if path not in {"/api/plan", "/api/records"}:
            self._send_json(404, {"error": "Route not found."})
            return

        try:
            payload = self._read_json_body()
            if path == "/api/plan":
                response = _plan_request(payload, self.server.kb)
                status = 200
            else:
                response, status = _save_record_request(
                    payload, self.server.record_store, self.server.kb
                )
        except _ResponseAlreadySent:
            return
        except InputValidationError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except InvalidRecordIdError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except RecordNotFoundError:
            self._send_json(404, {"error": "Saved record not found."})
            return
        except CorruptRecordError:
            self._send_json(500, {"error": "The saved record could not be updated."})
            return
        except OSError:
            _LOG.exception("Unable to save exploration record")
            self._send_json(500, {"error": "The saved record could not be saved."})
            return
        except Exception:
            _LOG.exception("Planner request failed")
            message = (
                "The planner could not process this request."
                if path == "/api/plan"
                else "The saved record could not be saved."
            )
            self._send_json(500, {"error": message})
            return
        self._send_json(status, response)

    def _read_json_body(self) -> Any:
        media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise InputValidationError("Content-Type must be application/json.")
        body = self._read_request_body(MAX_REQUEST_BYTES)
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

    def _read_exploration_body(self) -> bytes:
        content_type = self.headers.get("Content-Type", "")
        parts = content_type.split(";")
        if parts[0].strip().lower() != "application/x-ndjson":
            raise InputValidationError("Content-Type must be application/x-ndjson.")
        charset_seen = False
        for part in parts[1:]:
            name, separator, value = part.partition("=")
            charset = value.strip().strip('"').lower()
            if not separator or name.strip().lower() != "charset" or charset_seen or charset != "utf-8":
                raise InputValidationError(
                    "Content-Type may only include the charset=utf-8 parameter."
                )
            charset_seen = True
        return self._read_request_body(MAX_EXPLORATION_BYTES)

    def _read_request_body(self, maximum_bytes: int) -> bytes:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise InputValidationError("Content-Length is required.")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise InputValidationError("Content-Length must be a non-negative integer.") from exc
        if length < 0:
            raise InputValidationError("Content-Length must be a non-negative integer.")
        if length > maximum_bytes:
            self._send_json(413, {"error": f"Request body exceeds the {maximum_bytes}-byte limit."})
            raise _ResponseAlreadySent
        body = self.rfile.read(length)
        if len(body) != length:
            raise InputValidationError("Request body ended before Content-Length bytes were received.")
        return body

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

    def _send_checked_routes_js(self) -> None:
        try:
            content = CHECKED_ROUTES_JS_PATH.read_bytes()
        except OSError:
            self._send_json(404, {"error": "The checked-grid route script is not available."})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def _send_exploration_download(self, exploration_id: str, content: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="dst-exploration-{exploration_id}.jsonl"',
        )
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: Any) -> None:
        _LOG.info("%s - %s", self.address_string(), format % args)


class _ResponseAlreadySent(Exception):
    pass


def _save_record_request(payload: Any, store: RecordStore, kb=KB) -> tuple[dict[str, Any], int]:
    data = _require_mapping(payload, "request")
    allowed_fields = {"record_version", "id", "name", "world_note", "observation"}
    extra_fields = set(data) - allowed_fields
    if extra_fields:
        names = ", ".join(sorted(str(field) for field in extra_fields))
        raise InputValidationError(f"request has unsupported field(s): {names}.")
    if type(data.get("record_version")) is not int or data["record_version"] != 1:
        raise InputValidationError("request must use record_version 1.")

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InputValidationError("name must be a non-empty string.")
    name = name.strip()
    if len(name) > 120:
        raise InputValidationError("name must be at most 120 characters.")
    world_note = data.get("world_note")
    if not isinstance(world_note, str):
        raise InputValidationError("world_note must be a string.")
    if len(world_note) > 4096:
        raise InputValidationError("world_note must be at most 4096 characters.")

    observation = data.get("observation")
    validated_observation = _validated_observation_request(observation, kb)[0]
    record_id = None
    if "id" in data:
        record_id = data["id"]
        if not isinstance(record_id, str):
            raise InputValidationError("id must be a UUID.")
    record, created = store.save(
        name=name,
        world_note=world_note,
        observation=validated_observation,
        record_id=record_id,
    )
    return record, 201 if created else 200


def _background_recording_loop(server) -> None:
    while not server._background_recording_stop.is_set():
        try:
            target, seed = server.get_background_query()
            snapshots = read_snapshot_batch(server.live_log)
            for snapshot in snapshots:
                if server._background_recording_stop.is_set():
                    return
                if server.background_sequence_recorded(snapshot):
                    continue
                try:
                    _, age = freshness_status(snapshot, now=time.time())
                except LiveSnapshotError:
                    continue
                if (
                    age > FRESHNESS_SECONDS
                    or snapshot["world_kind"] not in {"forest", "cave"}
                ):
                    continue
                result = _live_snapshot_request(
                    snapshot,
                    target,
                    seed,
                    server.kb,
                    server.exploration_store,
                    plan_cache=server._live_plan_cache,
                    plan_cache_lock=server._live_plan_cache_lock,
                    stop_event=server._background_recording_stop,
                )
                if result.get("status") == "error":
                    recording = result.get("recording")
                    if recording and recording.get("status") == "error":
                        server.set_background_recording_error(
                            snapshot, recording.get("error", "recording failed")
                        )
                    _LOG.debug(
                        "Background recording skipped a live snapshot: %s",
                        result.get("error", "live snapshot is unavailable"),
                    )
                    # Leave this sequence eligible for retry and preserve log
                    # order so a later frame cannot make the failed frame stale.
                    break
                recording = result.get("recording")
                if recording is None:
                    if server._background_recording_stop.is_set():
                        return
                    break
                if recording.get("status") == "error":
                    server.set_background_recording_error(
                        snapshot, recording.get("error", "recording failed")
                    )
                    # Retry the failed sequence before appending later frames.
                    break
                else:
                    server.mark_background_sequence_recorded(snapshot)
        except Exception:
            _LOG.exception("Background live recording cycle failed")
        if server._background_recording_stop.wait(
            BACKGROUND_RECORDING_INTERVAL_SECONDS
        ):
            return


def create_server(
    port: int = 0,
    *,
    record_dir: Path | str | None = None,
    live_log: Path | str | None = None,
    exploration_dir: Path | str | None = None,
    background_recording: bool = True,
) -> ThreadingHTTPServer:
    """Create a local-only HTTP server; port 0 asks the OS for a free port."""
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("port must be an integer from 0 through 65535.")
    if type(background_recording) is not bool:
        raise ValueError("background_recording must be a boolean.")

    class PlannerHTTPServer(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

        def __init__(self, address):
            super().__init__(address, _PlannerHandler)
            self.kb = KB
            self.record_store = RecordStore(
                DEFAULT_RECORD_DIR if record_dir is None else Path(record_dir)
            )
            default_exploration_dir = (
                DEFAULT_RECORD_DIR.parent / "explorations"
                if record_dir is None
                else Path(record_dir).parent / "explorations"
            )
            self.exploration_store = ExplorationStore(
                default_exploration_dir if exploration_dir is None else Path(exploration_dir)
            )
            self.live_log = None if live_log is None else Path(live_log)
            self.background_recording = False
            self._background_recording_stop = threading.Event()
            self._background_recording_thread: threading.Thread | None = None
            self._background_query_lock = threading.Lock()
            self._background_query = ("panflute", 0)
            self._live_plan_cache: OrderedDict = OrderedDict()
            self._live_plan_cache_lock = threading.Lock()
            self._background_recording_state_lock = threading.Lock()
            self._background_recorded_sequences: OrderedDict = OrderedDict()
            self._background_recording_errors: OrderedDict = OrderedDict()

        def get_background_query(self) -> tuple[str, int]:
            with self._background_query_lock:
                return self._background_query

        def update_background_query(self, target: str, seed: int) -> None:
            with self._background_query_lock:
                self._background_query = (target, seed)

        def background_sequence_recorded(self, snapshot: Mapping[str, Any]) -> bool:
            identity = _snapshot_identity(snapshot)
            with self._background_recording_state_lock:
                if identity not in self._background_recorded_sequences:
                    return False
                self._background_recorded_sequences.move_to_end(identity)
                return True

        def mark_background_sequence_recorded(self, snapshot: Mapping[str, Any]) -> None:
            identity = _snapshot_identity(snapshot)
            recording_identity = _recording_identity(snapshot)
            with self._background_recording_state_lock:
                self._background_recorded_sequences[identity] = None
                self._background_recorded_sequences.move_to_end(identity)
                self._background_recording_errors.pop(recording_identity, None)
                while len(self._background_recorded_sequences) > BACKGROUND_RECORDED_SEQUENCE_CACHE_SIZE:
                    self._background_recorded_sequences.popitem(last=False)
                while len(self._background_recording_errors) > BACKGROUND_RECORDED_SEQUENCE_CACHE_SIZE:
                    self._background_recording_errors.popitem(last=False)

        def set_background_recording_error(
            self, snapshot: Mapping[str, Any], error: str
        ) -> None:
            identity = _recording_identity(snapshot)
            with self._background_recording_state_lock:
                self._background_recording_errors[identity] = error
                self._background_recording_errors.move_to_end(identity)
                while len(self._background_recording_errors) > BACKGROUND_RECORDED_SEQUENCE_CACHE_SIZE:
                    self._background_recording_errors.popitem(last=False)

        def background_recording_error(self, snapshot: Mapping[str, Any]) -> str | None:
            identity = _recording_identity(snapshot)
            with self._background_recording_state_lock:
                return self._background_recording_errors.get(identity)

        def start_background_recording(self) -> None:
            if self.live_log is None:
                return
            self.background_recording = True
            self._background_recording_thread = threading.Thread(
                target=_background_recording_loop,
                args=(self,),
                name="dst-route-planner-recorder",
                daemon=True,
            )
            try:
                self._background_recording_thread.start()
            except BaseException:
                self.background_recording = False
                self._background_recording_thread = None
                self._background_recording_stop.set()
                raise

        def server_close(self) -> None:
            self._background_recording_stop.set()
            thread = self._background_recording_thread
            try:
                if thread is not None and thread is not threading.current_thread():
                    thread.join(timeout=BACKGROUND_RECORDING_JOIN_TIMEOUT_SECONDS)
            finally:
                super().server_close()

    server = PlannerHTTPServer(("127.0.0.1", port))
    try:
        if background_recording and server.live_log is not None:
            server.start_background_recording()
        return server
    except BaseException:
        server.server_close()
        raise


def run_app(
    port: int = 8765,
    open_browser: bool = True,
    *,
    live_log: Path | str | None = None,
) -> None:
    """Run the local planner app until interrupted with Ctrl+C."""
    server = create_server(port, live_log=live_log)
    address, actual_port = server.server_address[:2]
    url = f"http://{address}:{actual_port}/"
    print(f"DST Route Planner is available at {url}")
    if server.background_recording:
        print("Background exploration recording continues until you exit the tool.")
    try:
        if open_browser:
            webbrowser.open(url, new=2)
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
