from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dst_route_planner.live import validate_snapshot


REPLAY_VERSION = 1
MAX_EXPLORATION_BYTES = 32 * 1024 * 1024
MAX_EXPLORATION_FRAMES = 10_000
MAX_EXPLORATION_SEGMENT = 2**53 - 1
MAX_HEADER_LINE_BYTES = 64 * 1024
JOURNAL_LOCK_TIMEOUT_SECONDS = 1.0
_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_STORE_LOCKS_GUARD = threading.Lock()
_STORE_LOCKS: dict[str, Any] = {}


class ExplorationError(Exception):
    """Base class for exploration journal failures."""


class InvalidExplorationIdError(ExplorationError, ValueError):
    """Raised when a journal ID is not a lowercase SHA256 hex string."""


class ExplorationNotFoundError(ExplorationError):
    """Raised when a journal does not exist."""


class CorruptExplorationError(ExplorationError):
    """Raised when a complete journal line is malformed or inconsistent."""


class ExplorationLockError(OSError):
    """Raised when another process holds a journal lock for too long."""


class ExplorationConflictError(ExplorationError):
    """Raised when a different replay already uses the imported identity."""


class ExplorationTooLargeError(ExplorationError):
    """Raised when an import exceeds replay size or frame limits."""


@dataclass(frozen=True)
class _JournalMetadata:
    header: dict[str, Any]
    frame_count: int
    started_at: str | None
    last_captured_at: str | None
    first_sequence: int
    last_sequence: int
    complete_size: int
    file_size: int
    mtime_ns: int


def exploration_id(
    world_id: str, world_kind: str, session_id: str, *, segment: int = 1
) -> str:
    if type(segment) is not int or not 1 <= segment <= MAX_EXPLORATION_SEGMENT:
        raise ValueError(f"segment must be an integer from 1 to {MAX_EXPLORATION_SEGMENT}.")
    identity_values = [world_id, world_kind, session_id]
    if segment >= 2:
        identity_values.append(segment)
    identity = json.dumps(identity_values, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(identity).hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _captured_at_timestamp(value: int | float) -> str:
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )
    except (OverflowError, OSError, ValueError) as exc:
        raise CorruptExplorationError("snapshot captured_at is outside the supported range.") from exc


def _parse_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise CorruptExplorationError(f"{label} must be a timestamp string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CorruptExplorationError(f"{label} is invalid.") from exc
    if parsed.tzinfo is None:
        raise CorruptExplorationError(f"{label} must include a timezone.")
    return value


def _json_line(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
        "utf-8"
    ) + b"\n"


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _summary(
    header: dict[str, Any],
    *,
    frame_count: int,
    started_at: str | None,
    last_captured_at: str | None,
    byte_count: int,
    status: str | None = None,
) -> dict[str, Any]:
    if status is None:
        status = (
            "limit_reached"
            if frame_count >= MAX_EXPLORATION_FRAMES or byte_count >= MAX_EXPLORATION_BYTES
            else "recording"
        )
    summary = {
        "id": header["id"],
        "world_id": header["world_id"],
        "world_kind": header["world_kind"],
        "session_id": header["session_id"],
        "frame_count": frame_count,
        "started_at": started_at,
        "last_captured_at": last_captured_at,
        "status": status,
    }
    if "segment" in header:
        summary["segment"] = header["segment"]
    return summary


def _metadata_summary(
    metadata: _JournalMetadata, *, status: str | None = None
) -> dict[str, Any]:
    return _summary(
        metadata.header,
        frame_count=metadata.frame_count,
        started_at=metadata.started_at,
        last_captured_at=metadata.last_captured_at,
        byte_count=metadata.complete_size,
        status=status,
    )


def _extract_import_id(raw: bytes) -> str | None:
    """Return a syntactically valid header ID so the shared reader can validate it."""
    first_line = raw.split(b"\n", 1)[0]
    try:
        header = json.loads(
            first_line.decode("utf-8"),
            object_pairs_hook=_object_no_duplicates,
            parse_constant=ExplorationStore._reject_constant,
            parse_float=ExplorationStore._parse_finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(header, dict):
        return None
    try:
        return ExplorationStore.normalize_id(header.get("id"))
    except InvalidExplorationIdError:
        return None


class ExplorationStore:
    """Append and serve local JSONL replays from live collector snapshots."""

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)
        lock_key = str(self.directory.resolve()).casefold()
        with _STORE_LOCKS_GUARD:
            self._lock = _STORE_LOCKS.setdefault(lock_key, threading.RLock())
        self._metadata_cache: dict[str, _JournalMetadata] = {}
        self._session_segments: dict[tuple[str, str, str], int] = {}
        self._segment_index_mtime_ns: int | None = None

    def capture(
        self,
        snapshot: dict[str, Any],
        *,
        target: str,
        seed: int,
        plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # The live reader validates snapshots already; repeat validation at this
        # persistence boundary so callers cannot put malformed data in a replay.
        validated = validate_snapshot(snapshot)
        world_id = validated["world_id"]
        world_kind = validated["world_kind"]
        session_id = validated["session_id"]
        base_identity = (world_id, world_kind, session_id)
        base_id = exploration_id(*base_identity)
        frame: dict[str, Any] = {
            "replay_version": REPLAY_VERSION,
            "received_at": _timestamp(),
            "target": target,
            "seed": seed,
            "snapshot": validated,
        }
        if plan is not None:
            frame["plan"] = plan
        frame_bytes = _json_line(frame)
        with self._lock, self._session_file_lock(base_id):
            self.directory.mkdir(parents=True, exist_ok=True)
            self._refresh_segment_index()
            segment = self._active_segment(base_identity)

            while True:
                journal_id = exploration_id(*base_identity, segment=segment)
                header = self._make_header(*base_identity, segment=segment)
                header_bytes = _json_line(header)
                path = self._journal_path(journal_id)
                with self._journal_file_lock(journal_id):
                    if path.is_symlink():
                        raise CorruptExplorationError("journal path is not a regular file.")
                    exists = path.exists()
                    if exists:
                        metadata = self._read_metadata(path, journal_id)
                    else:
                        self._metadata_cache.pop(journal_id, None)
                        metadata = _JournalMetadata(
                            header=header,
                            frame_count=0,
                            started_at=None,
                            last_captured_at=None,
                            first_sequence=0,
                            last_sequence=0,
                            complete_size=0,
                            file_size=0,
                            mtime_ns=0,
                        )

                    summary = _metadata_summary(metadata)
                    # Check sequence before considering capacity so duplicate or
                    # stale collector snapshots never create a new part.
                    if metadata.frame_count and validated["sequence"] <= metadata.last_sequence:
                        return summary

                    append_bytes = frame_bytes if exists else header_bytes + frame_bytes
                    projected_size = metadata.complete_size + len(append_bytes)
                    fits = (
                        metadata.frame_count + 1 <= MAX_EXPLORATION_FRAMES
                        and projected_size <= MAX_EXPLORATION_BYTES
                    )
                    if fits:
                        if exists and metadata.file_size > metadata.complete_size:
                            with path.open("r+b") as journal:
                                journal.truncate(metadata.complete_size)
                                journal.flush()
                        with path.open("ab") as journal:
                            journal.write(append_bytes)
                            journal.flush()

                        stat = path.stat()
                        updated = _JournalMetadata(
                            header=metadata.header,
                            frame_count=metadata.frame_count + 1,
                            started_at=metadata.started_at or frame["received_at"],
                            last_captured_at=_captured_at_timestamp(validated["captured_at"]),
                            first_sequence=metadata.first_sequence or validated["sequence"],
                            last_sequence=validated["sequence"],
                            complete_size=projected_size,
                            file_size=stat.st_size,
                            mtime_ns=stat.st_mtime_ns,
                        )
                        self._metadata_cache[journal_id] = updated
                        if segment > self._session_segments.get(base_identity, 0):
                            self._session_segments[base_identity] = segment
                        if not exists:
                            # The directory changed. Force a bounded header-only
                            # refresh on the next discovery operation.
                            self._segment_index_mtime_ns = None
                        return _metadata_summary(updated)

                    # Later part headers are longer, so check the next part
                    # before advancing or returning a summary for a missing file.
                    if MAX_EXPLORATION_FRAMES < 1 or segment == MAX_EXPLORATION_SEGMENT:
                        return _metadata_summary(metadata, status="limit_reached")
                    next_header = _json_line(
                        self._make_header(*base_identity, segment=segment + 1)
                    )
                    if len(next_header) + len(frame_bytes) > MAX_EXPLORATION_BYTES:
                        return _metadata_summary(metadata, status="limit_reached")
                segment += 1

    def import_bytes(self, raw: bytes) -> tuple[dict[str, Any], bool]:
        """Validate and atomically import one complete JSONL replay."""
        if not isinstance(raw, bytes):
            raise CorruptExplorationError("replay body must be bytes.")
        if len(raw) > MAX_EXPLORATION_BYTES:
            raise ExplorationTooLargeError("exploration exceeds the configured size limit.")
        if not raw:
            raise CorruptExplorationError("journal is empty.")
        normalized = raw if raw.endswith(b"\n") else raw + b"\n"
        if len(normalized) > MAX_EXPLORATION_BYTES:
            raise ExplorationTooLargeError("exploration exceeds the configured size limit.")

        # Terminate the final input line before using the journal reader. That
        # preserves its recovery behavior for interrupted on-disk appends while
        # ensuring an invalid imported tail cannot be silently ignored.
        header_id = _extract_import_id(normalized)
        expected_id = header_id if header_id is not None else ""
        header, frames, complete_size = self._read_journal_bytes(normalized, expected_id)
        if not frames:
            raise CorruptExplorationError("journal must contain at least one frame.")
        if len(frames) > MAX_EXPLORATION_FRAMES:
            raise ExplorationTooLargeError("exploration exceeds the configured frame limit.")
        for frame in frames:
            _captured_at_timestamp(frame["snapshot"]["captured_at"])
        if complete_size != len(normalized):
            raise CorruptExplorationError("journal contains an incomplete line.")

        journal_id = header["id"]
        base_identity = (header["world_id"], header["world_kind"], header["session_id"])
        base_id = exploration_id(*base_identity)
        path = self._journal_path(journal_id)
        with self._lock, self._session_file_lock(base_id), self._journal_file_lock(journal_id):
            self.directory.mkdir(parents=True, exist_ok=True)
            self._refresh_segment_index()
            if path.is_symlink():
                raise ExplorationConflictError("an exploration already exists at this identity.")
            if path.exists():
                summary = self._import_existing(path, journal_id, header, frames)
                self._session_segments[base_identity] = max(
                    self._session_segments.get(base_identity, 0), header.get("segment", 1)
                )
                return summary, False
            self._validate_import_segment_order(
                base_identity,
                header.get("segment", 1),
                journal_id,
                frames,
            )

            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=self.directory,
                    prefix=f".{journal_id}.import-",
                    suffix=".tmp",
                    delete=False,
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    temporary.write(normalized)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                try:
                    if os.name == "nt":
                        # Windows rename is atomic and fails when the destination
                        # already exists.
                        os.rename(temporary_path, path)
                        temporary_path = None
                    else:
                        # A hard link publishes the fully written file atomically
                        # and cannot replace a file created by another process.
                        os.link(temporary_path, path)
                except FileExistsError:
                    if path.is_symlink():
                        raise ExplorationConflictError(
                            "an exploration already exists at this identity."
                        )
                    summary = self._import_existing(path, journal_id, header, frames)
                    self._session_segments[base_identity] = max(
                        self._session_segments.get(base_identity, 0),
                        header.get("segment", 1),
                    )
                    return summary, False
                finally:
                    if temporary_path is not None:
                        try:
                            temporary_path.unlink()
                        except OSError:
                            pass

                stat = path.stat()
                metadata = _JournalMetadata(
                    header=header,
                    frame_count=len(frames),
                    started_at=frames[0]["received_at"],
                    last_captured_at=_captured_at_timestamp(
                        frames[-1]["snapshot"]["captured_at"]
                    ),
                    first_sequence=frames[0]["snapshot"]["sequence"],
                    last_sequence=frames[-1]["snapshot"]["sequence"],
                    complete_size=len(normalized),
                    file_size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                )
                self._metadata_cache[journal_id] = metadata
                self._session_segments[base_identity] = max(
                    self._session_segments.get(base_identity, 0), header.get("segment", 1)
                )
                self._segment_index_mtime_ns = None
                return _metadata_summary(metadata), True
            finally:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink()
                    except OSError:
                        pass

    def _import_existing(
        self,
        path: Path,
        journal_id: str,
        imported_header: dict[str, Any],
        imported_frames: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if path.is_symlink():
            raise ExplorationConflictError("an exploration already exists at this identity.")
        try:
            metadata = self._read_metadata(path, journal_id)
            with path.open("rb") as journal:
                existing = journal.read(metadata.complete_size)
            stat = path.stat()
            if (stat.st_size, stat.st_mtime_ns) != (metadata.file_size, metadata.mtime_ns):
                self._metadata_cache.pop(journal_id, None)
                raise CorruptExplorationError("journal changed while it was being compared.")
            if len(existing) != metadata.complete_size:
                raise CorruptExplorationError("journal ended before its complete content was read.")
            existing_header, existing_frames, _ = self._read_journal_bytes(existing, journal_id)
        except (OSError, CorruptExplorationError) as exc:
            raise ExplorationConflictError(
                "an unreadable exploration already exists at this identity."
            ) from exc
        if existing_header != imported_header or existing_frames != imported_frames:
            raise ExplorationConflictError(
                "a different exploration already exists for this world and session."
            )
        return _metadata_summary(metadata)

    def _validate_import_segment_order(
        self,
        identity: tuple[str, str, str],
        imported_segment: int,
        imported_id: str,
        imported_frames: list[dict[str, Any]],
    ) -> None:
        """Keep imported sibling journals in cumulative sequence order."""
        imported_first = imported_frames[0]["snapshot"]["sequence"]
        imported_last = imported_frames[-1]["snapshot"]["sequence"]
        for path in self.directory.iterdir():
            if path.suffix != ".jsonl" or path.is_symlink():
                continue
            sibling_id = path.stem
            if sibling_id == imported_id or not _ID_PATTERN.fullmatch(sibling_id):
                continue
            with self._journal_file_lock(sibling_id):
                if path.is_symlink():
                    continue
                try:
                    sibling_header, sibling_segment = self._read_header_line(path, sibling_id)
                except (OSError, CorruptExplorationError):
                    # Unrelated malformed journals do not prevent importing a
                    # valid replay, matching list_explorations behavior.
                    continue
                sibling_identity = (
                    sibling_header["world_id"],
                    sibling_header["world_kind"],
                    sibling_header["session_id"],
                )
                if sibling_identity != identity or sibling_segment == imported_segment:
                    continue
                try:
                    metadata = self._read_metadata(path, sibling_id)
                except (OSError, CorruptExplorationError) as exc:
                    raise ExplorationConflictError(
                        "a sibling exploration cannot be validated."
                    ) from exc
                if metadata.frame_count == 0:
                    continue
                if sibling_segment < imported_segment:
                    ordered = metadata.last_sequence < imported_first
                else:
                    ordered = metadata.first_sequence > imported_last
                if not ordered:
                    raise ExplorationConflictError(
                        "sibling exploration sequence ranges overlap or are out of order."
                    )

    def summary_for_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        """Return a matching journal summary without changing its file."""
        validated = validate_snapshot(snapshot)
        base_identity = (
            validated["world_id"],
            validated["world_kind"],
            validated["session_id"],
        )
        base_id = exploration_id(*base_identity)
        with self._lock, self._session_file_lock(base_id):
            self._refresh_segment_index()
            segment = self._active_segment(base_identity)
            journal_id = exploration_id(*base_identity, segment=segment)
            path = self._journal_path(journal_id)
            try:
                with self._journal_file_lock(journal_id):
                    metadata = self._read_metadata(path, journal_id)
            except FileNotFoundError:
                return None
            if metadata.frame_count == 0:
                return None
            return _metadata_summary(metadata)

    def list_explorations(self) -> list[dict[str, Any]]:
        self.directory.mkdir(parents=True, exist_ok=True)
        summaries: list[dict[str, Any]] = []
        with self._lock:
            for path in self.directory.iterdir():
                if path.suffix != ".jsonl" or not path.is_file() or path.is_symlink():
                    continue
                journal_id = path.stem
                if not _ID_PATTERN.fullmatch(journal_id):
                    continue
                try:
                    with self._journal_file_lock(journal_id):
                        metadata = self._read_metadata(path, journal_id)
                except (OSError, CorruptExplorationError):
                    continue
                if metadata.frame_count:
                    summaries.append(_metadata_summary(metadata))
        summaries.sort(
            key=lambda item: (
                item["last_captured_at"] or "",
                item["started_at"] or "",
                item["id"],
            ),
            reverse=True,
        )
        return summaries

    def get_bytes(self, journal_id: str) -> bytes:
        normalized_id = self.normalize_id(journal_id)
        path = self._journal_path(normalized_id)
        try:
            with self._lock, self._journal_file_lock(normalized_id):
                if path.is_symlink():
                    raise ExplorationNotFoundError("exploration not found")
                metadata = self._read_metadata(path, normalized_id)
                with path.open("rb") as journal:
                    complete_content = journal.read(metadata.complete_size)
                stat = path.stat()
                if (stat.st_size, stat.st_mtime_ns) != (metadata.file_size, metadata.mtime_ns):
                    self._metadata_cache.pop(normalized_id, None)
                    raise CorruptExplorationError("journal changed while it was being exported.")
                if len(complete_content) != metadata.complete_size:
                    raise CorruptExplorationError("journal ended before its complete content was read.")
                return complete_content
        except FileNotFoundError as exc:
            raise ExplorationNotFoundError("exploration not found") from exc

    @staticmethod
    def normalize_id(value: Any) -> str:
        if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
            raise InvalidExplorationIdError("id must be a 64-character lowercase hexadecimal string.")
        return value

    def _journal_path(self, normalized_id: str) -> Path:
        return self.directory / f"{normalized_id}.jsonl"

    @contextmanager
    def _journal_file_lock(self, journal_id: str):
        with self._named_file_lock(f".{journal_id}.lock"):
            yield

    @contextmanager
    def _session_file_lock(self, base_id: str):
        # This lock has a distinct name from the base journal's lock, including
        # for segment 1, so acquiring both cannot self-deadlock.
        with self._named_file_lock(f".session-{base_id}.lock"):
            yield

    @contextmanager
    def _named_file_lock(self, lock_name: str):
        self.directory.mkdir(parents=True, exist_ok=True)
        lock_path = self.directory / lock_name
        with lock_path.open("a+b") as lock_file:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            deadline = time.monotonic() + JOURNAL_LOCK_TIMEOUT_SECONDS
            locked = False
            while not locked:
                try:
                    if os.name == "nt":
                        import msvcrt

                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise ExplorationLockError("exploration journal is busy.") from exc
                    time.sleep(0.01)
            try:
                yield
            finally:
                if os.name == "nt":
                    import msvcrt

                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _make_header(
        world_id: str, world_kind: str, session_id: str, *, segment: int = 1
    ) -> dict[str, Any]:
        header: dict[str, Any] = {
            "replay_version": REPLAY_VERSION,
            "id": exploration_id(world_id, world_kind, session_id, segment=segment),
            "world_id": world_id,
            "world_kind": world_kind,
            "session_id": session_id,
        }
        if segment >= 2:
            header["segment"] = segment
        return header

    def _validate_header(self, header: Any, expected_id: str) -> tuple[dict[str, Any], int]:
        base_fields = {"replay_version", "id", "world_id", "world_kind", "session_id"}
        if not isinstance(header, dict):
            raise CorruptExplorationError("journal header fields are invalid.")
        if set(header) not in (base_fields, base_fields | {"segment"}):
            raise CorruptExplorationError("journal header fields are invalid.")
        if type(header["replay_version"]) is not int or header["replay_version"] != REPLAY_VERSION:
            raise CorruptExplorationError("journal replay version is unsupported.")
        for key in ("world_id", "world_kind", "session_id"):
            if not isinstance(header[key], str) or not header[key].strip():
                raise CorruptExplorationError("journal identity fields are invalid.")
        segment = 1
        if "segment" in header:
            segment = header["segment"]
            if (
                type(segment) is not int
                or segment < 2
                or segment > MAX_EXPLORATION_SEGMENT
            ):
                raise CorruptExplorationError("journal segment is invalid.")
        try:
            stored_id = self.normalize_id(header["id"])
            identity_id = exploration_id(
                header["world_id"],
                header["world_kind"],
                header["session_id"],
                segment=segment,
            )
        except (InvalidExplorationIdError, TypeError, ValueError) as exc:
            raise CorruptExplorationError("journal identity is invalid.") from exc
        if stored_id != expected_id or identity_id != stored_id:
            raise CorruptExplorationError("journal identity does not match its filename.")
        return header, segment

    def _read_header_line(self, path: Path, expected_id: str) -> tuple[dict[str, Any], int]:
        try:
            with path.open("rb") as journal:
                raw_line = journal.readline(MAX_HEADER_LINE_BYTES + 1)
        except OSError:
            raise
        if len(raw_line) > MAX_HEADER_LINE_BYTES or not raw_line.endswith(b"\n"):
            raise CorruptExplorationError("journal header line is incomplete or too large.")
        try:
            header = json.loads(
                raw_line.decode("utf-8"),
                object_pairs_hook=_object_no_duplicates,
                parse_constant=self._reject_constant,
                parse_float=self._parse_finite_float,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise CorruptExplorationError("journal header is invalid.") from exc
        return self._validate_header(header, expected_id)

    def _refresh_segment_index(self) -> None:
        """Refresh session-to-segment hints by reading bounded header lines only."""
        try:
            current_mtime = self.directory.stat().st_mtime_ns
        except FileNotFoundError:
            self._session_segments = {}
            self._segment_index_mtime_ns = None
            return
        if self._segment_index_mtime_ns == current_mtime:
            return

        latest_segments: dict[tuple[str, str, str], int] = {}
        observed_mtime = current_mtime
        for _ in range(4):
            try:
                before_mtime = self.directory.stat().st_mtime_ns
            except FileNotFoundError:
                self._session_segments = {}
                self._segment_index_mtime_ns = None
                return
            latest_segments = {}
            try:
                paths = tuple(self.directory.iterdir())
            except FileNotFoundError:
                paths = ()
            for path in paths:
                if path.suffix != ".jsonl" or path.is_symlink():
                    continue
                journal_id = path.stem
                if not _ID_PATTERN.fullmatch(journal_id):
                    continue
                try:
                    header, segment = self._read_header_line(path, journal_id)
                except (OSError, CorruptExplorationError):
                    continue
                identity = (header["world_id"], header["world_kind"], header["session_id"])
                latest_segments[identity] = max(latest_segments.get(identity, 0), segment)
            try:
                after_mtime = self.directory.stat().st_mtime_ns
            except FileNotFoundError:
                self._session_segments = {}
                self._segment_index_mtime_ns = None
                return
            observed_mtime = before_mtime
            if before_mtime == after_mtime:
                observed_mtime = after_mtime
                break
        self._session_segments = latest_segments
        # If files changed during all attempts, keep the pre-scan timestamp so
        # the next lookup retries the cheap header-only discovery pass.
        self._segment_index_mtime_ns = observed_mtime

    def _active_segment(self, identity: tuple[str, str, str]) -> int:
        segment = self._session_segments.get(identity, 1)
        while segment < MAX_EXPLORATION_SEGMENT:
            next_segment = segment + 1
            next_id = exploration_id(*identity, segment=next_segment)
            next_path = self._journal_path(next_id)
            if not next_path.exists() and not next_path.is_symlink():
                break
            with self._journal_file_lock(next_id):
                # A corrupt expected sibling must be reported, never replaced.
                metadata = self._read_metadata(next_path, next_id)
            if (
                metadata.header["world_id"],
                metadata.header["world_kind"],
                metadata.header["session_id"],
            ) != identity:
                raise CorruptExplorationError("journal identity does not match its session.")
            segment = next_segment
        self._session_segments[identity] = segment
        return segment

    def _read_metadata(self, path: Path, journal_id: str) -> _JournalMetadata:
        if path.is_symlink():
            raise CorruptExplorationError("journal path is not a regular file.")
        before = path.stat()
        cached = self._metadata_cache.get(journal_id)
        if cached is not None and (cached.file_size, cached.mtime_ns) == (
            before.st_size,
            before.st_mtime_ns,
        ):
            return cached
        if before.st_size > MAX_EXPLORATION_BYTES:
            raise CorruptExplorationError("journal exceeds the configured size limit.")
        raw = path.read_bytes()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or len(raw) != after.st_size:
            raise CorruptExplorationError("journal changed while it was being read.")
        header, frames, complete_size = self._read_journal_bytes(raw, journal_id)
        metadata = _JournalMetadata(
            header=header,
            frame_count=len(frames),
            started_at=frames[0]["received_at"] if frames else None,
            last_captured_at=(
                _captured_at_timestamp(frames[-1]["snapshot"]["captured_at"])
                if frames
                else None
            ),
            first_sequence=frames[0]["snapshot"]["sequence"] if frames else 0,
            last_sequence=frames[-1]["snapshot"]["sequence"] if frames else 0,
            complete_size=complete_size,
            file_size=after.st_size,
            mtime_ns=after.st_mtime_ns,
        )
        self._metadata_cache[journal_id] = metadata
        return metadata

    def _read_journal_bytes(
        self, raw: bytes, expected_id: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        if len(raw) > MAX_EXPLORATION_BYTES:
            raise CorruptExplorationError("journal exceeds the configured size limit.")
        if not raw:
            raise CorruptExplorationError("journal is empty.")
        last_newline = raw.rfind(b"\n")
        if last_newline < 0:
            raise CorruptExplorationError("journal has no complete header line.")
        complete_size = last_newline + 1
        complete = raw[:complete_size]
        lines = complete.splitlines()
        if not lines:
            raise CorruptExplorationError("journal has no header line.")
        values: list[Any] = []
        try:
            for line in lines:
                values.append(
                    json.loads(
                        line.decode("utf-8"),
                        object_pairs_hook=_object_no_duplicates,
                        parse_constant=self._reject_constant,
                        parse_float=self._parse_finite_float,
                    )
                )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
            raise CorruptExplorationError("journal contains an invalid complete JSON line.") from exc

        header, _segment = self._validate_header(values[0], expected_id)

        frames: list[dict[str, Any]] = []
        previous_sequence = 0
        required_frame_fields = {"replay_version", "received_at", "target", "seed", "snapshot"}
        for value in values[1:]:
            if not isinstance(value, dict) or not required_frame_fields <= set(value) or set(value) - (
                required_frame_fields | {"plan"}
            ):
                raise CorruptExplorationError("journal frame fields are invalid.")
            if type(value["replay_version"]) is not int or value["replay_version"] != REPLAY_VERSION:
                raise CorruptExplorationError("journal frame version is unsupported.")
            _parse_timestamp(value["received_at"], "received_at")
            if not isinstance(value["target"], str) or not value["target"].strip():
                raise CorruptExplorationError("journal frame target is invalid.")
            if type(value["seed"]) is not int:
                raise CorruptExplorationError("journal frame seed is invalid.")
            try:
                snapshot = validate_snapshot(value["snapshot"])
            except Exception as exc:
                raise CorruptExplorationError("journal frame snapshot is invalid.") from exc
            if any(
                snapshot[key] != header[key]
                for key in ("world_id", "world_kind", "session_id")
            ):
                raise CorruptExplorationError("journal frame belongs to a different session.")
            if snapshot["sequence"] <= previous_sequence:
                raise CorruptExplorationError("journal frame sequences are not increasing.")
            if "plan" in value and not isinstance(value["plan"], dict):
                raise CorruptExplorationError("journal frame plan is invalid.")
            previous_sequence = snapshot["sequence"]
            frames.append(value)
        return header, frames, complete_size

    @staticmethod
    def _parse_finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite JSON number")
        return number

    @staticmethod
    def _reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant {value}")
