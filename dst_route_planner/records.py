from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RECORD_VERSION = 1
_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class RecordError(Exception):
    """Base class for saved-record failures."""


class InvalidRecordIdError(RecordError, ValueError):
    """Raised when a record ID is not a canonical UUID string."""


class RecordNotFoundError(RecordError):
    """Raised when a selected record does not exist."""


class CorruptRecordError(RecordError):
    """Raised when a selected record file cannot be read as a record."""


def normalize_record_id(value: Any) -> str:
    if not isinstance(value, str) or not _UUID_PATTERN.fullmatch(value):
        raise InvalidRecordIdError("id must be a UUID.")
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise InvalidRecordIdError("id must be a UUID.") from exc


def _validated_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("name must be a non-empty string.")
    name = value.strip()
    if len(name) > 120:
        raise ValueError("name must be at most 120 characters.")
    return name


def _validated_world_note(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("world_note must be a string.")
    if len(value) > 4096:
        raise ValueError("world_note must be at most 4096 characters.")
    return value


def _read_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise CorruptRecordError("record saved_at must be a timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CorruptRecordError("record saved_at is invalid") from exc
    if parsed.tzinfo is None:
        raise CorruptRecordError("record saved_at must include a timezone")
    return value


class RecordStore:
    """Persist small versioned exploration records as individual JSON files."""

    def __init__(self, directory: Path | str):
        self.directory = Path(directory)

    def list_records(
        self,
        *,
        observation_validator: Callable[[Any], Any] | None = None,
    ) -> list[dict[str, str]]:
        self.directory.mkdir(parents=True, exist_ok=True)
        records: list[dict[str, str]] = []
        for path in self.directory.iterdir():
            if path.suffix != ".json" or not path.is_file():
                continue
            try:
                record_id = normalize_record_id(path.stem)
                record = self._read_file(path, record_id)
                if observation_validator is not None:
                    observation_validator(record["observation"])
                target = record["observation"].get("target")
                if not isinstance(target, str) or not target.strip():
                    continue
                records.append(
                    {
                        "id": record["id"],
                        "name": record["name"],
                        "target": target,
                        "saved_at": record["saved_at"],
                    }
                )
            except Exception:
                # A manually removed, old, or damaged file should not hide other records.
                continue
        records.sort(key=lambda item: (item["saved_at"], item["id"]), reverse=True)
        return records

    def get(self, record_id: str) -> dict[str, Any]:
        normalized_id = normalize_record_id(record_id)
        path = self._record_path(normalized_id)
        try:
            return self._read_file(path, normalized_id)
        except FileNotFoundError as exc:
            raise RecordNotFoundError("saved record not found") from exc

    def save(
        self,
        *,
        name: str,
        world_note: str,
        observation: Mapping[str, Any],
        record_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        normalized_name = _validated_name(name)
        normalized_note = _validated_world_note(world_note)
        if not isinstance(observation, Mapping):
            raise ValueError("observation must be a JSON object.")
        if record_id is None:
            normalized_id = str(uuid.uuid4())
            created = True
        else:
            normalized_id = normalize_record_id(record_id)
            self.get(normalized_id)
            created = False

        record = {
            "record_version": RECORD_VERSION,
            "id": normalized_id,
            "name": normalized_name,
            "world_note": normalized_note,
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
            "observation": dict(observation),
        }
        self._write_atomically(self._record_path(normalized_id), record)
        return record, created

    def _record_path(self, normalized_id: str) -> Path:
        return self.directory / f"{normalized_id}.json"

    def _read_file(self, path: Path, expected_id: str) -> dict[str, Any]:
        try:
            raw = path.read_text(encoding="utf-8")
            record = json.loads(raw, parse_constant=self._reject_json_constant)
        except FileNotFoundError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise CorruptRecordError("record file is not valid UTF-8 JSON") from exc

        if not isinstance(record, dict):
            raise CorruptRecordError("record must be a JSON object")
        expected_fields = {"record_version", "id", "name", "world_note", "saved_at", "observation"}
        if set(record) != expected_fields:
            raise CorruptRecordError("record fields are invalid")
        if type(record["record_version"]) is not int or record["record_version"] != RECORD_VERSION:
            raise CorruptRecordError("record version is unsupported")
        try:
            stored_id = normalize_record_id(record["id"])
            name = _validated_name(record["name"])
            world_note = _validated_world_note(record["world_note"])
        except (InvalidRecordIdError, ValueError, TypeError) as exc:
            raise CorruptRecordError("record metadata is invalid") from exc
        if stored_id != expected_id or name != record["name"]:
            raise CorruptRecordError("record identity or name is invalid")
        if not isinstance(record["observation"], dict):
            raise CorruptRecordError("record observation must be an object")
        saved_at = _read_timestamp(record["saved_at"])
        return {
            "record_version": RECORD_VERSION,
            "id": stored_id,
            "name": name,
            "world_note": world_note,
            "saved_at": saved_at,
            "observation": record["observation"],
        }

    @staticmethod
    def _reject_json_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant {value}")

    def _write_atomically(self, path: Path, record: Mapping[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=f".{path.stem}.",
                suffix=".tmp",
                dir=self.directory,
                delete=False,
            ) as output:
                temporary_path = Path(output.name)
                json.dump(record, output, ensure_ascii=False, allow_nan=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass