"""Install or update the bundled DST client collector."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "mods" / "dst_route_collector"
RUNTIME_FILES = ("collector.lua", "modmain.lua", "modinfo.lua")
_VERSION_RE = re.compile(r"(?m)^\s*version\s*=\s*(['\"])([^'\"]+)\1\s*(?:--.*)?$")


class CollectorInstallError(ValueError):
    """Raised when the selected mods folder or bundled collector is invalid."""


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _load_bundle(source_dir: Path) -> tuple[dict[str, bytes], str, Path]:
    if source_dir.is_symlink() or not source_dir.is_dir():
        raise CollectorInstallError(f"Collector bundle not found: {source_dir}")
    source = source_dir.resolve(strict=True)
    files: dict[str, bytes] = {}
    for name in RUNTIME_FILES:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise CollectorInstallError(f"Collector bundle is missing a regular {name}")
        files[name] = path.read_bytes()
    try:
        modinfo = files["modinfo.lua"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CollectorInstallError("Collector modinfo.lua is not valid UTF-8") from exc
    match = _VERSION_RE.search(modinfo)
    if not match:
        raise CollectorInstallError("Collector modinfo.lua has no valid version field")
    return files, match.group(2), source


def _cleanup_stage(stage: Path, changed_names: tuple[str, ...]) -> None:
    for folder in (stage / "new", stage / "old"):
        for name in changed_names:
            try:
                (folder / name).unlink(missing_ok=True)
            except OSError:
                pass
        try:
            folder.rmdir()
        except OSError:
            pass
    try:
        stage.rmdir()
    except OSError:
        pass


def _cleanup_backup(backup_dir: Path, names: tuple[str, ...]) -> None:
    for name in names:
        try:
            (backup_dir / name).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        backup_dir.rmdir()
    except OSError:
        pass


def _write_backup(
    backup_root: Path, previous: dict[str, bytes], names: tuple[str, ...]
) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(
        tempfile.mkdtemp(prefix="dst-route-collector-", dir=str(backup_root))
    ).resolve()
    try:
        for name in names:
            (backup_dir / name).write_bytes(previous[name])
    except OSError:
        _cleanup_backup(backup_dir, names)
        raise
    return backup_dir


def install_collector(
    mods_dir: Path | str, *, backup_root: Path | str | None = None
) -> dict[str, object]:
    """Install or update the three runtime files in an explicitly chosen mods folder.

    Existing changed runtime files are copied to a unique backup directory before
    replacement. Files unrelated to the collector are left alone.
    """

    raw_mods_dir = Path(mods_dir).expanduser()
    if raw_mods_dir.name.casefold() != "mods":
        raise CollectorInstallError("Choose the game's existing mods folder")
    if raw_mods_dir.is_symlink() and not raw_mods_dir.is_dir():
        raise CollectorInstallError("The selected mods path is not a directory")
    if not raw_mods_dir.exists() or not raw_mods_dir.is_dir():
        raise CollectorInstallError("The selected mods folder does not exist")
    mods = raw_mods_dir.resolve(strict=True)

    files, version, source = _load_bundle(Path(SOURCE_DIR))
    destination = mods / "dst_route_collector"
    if destination.is_symlink():
        raise CollectorInstallError("Collector destination must not be a symlink")
    if destination.exists() and not destination.is_dir():
        raise CollectorInstallError("Collector destination is not a directory")
    destination_resolved = destination.resolve(strict=False)
    if destination_resolved.parent != mods:
        raise CollectorInstallError("Collector destination resolves outside the selected mods folder")
    if (
        destination_resolved == source
        or _inside(destination_resolved, source)
        or _inside(source, destination_resolved)
    ):
        raise CollectorInstallError("Collector source and destination overlap")

    destination_exists = destination.exists()
    previous: dict[str, bytes] = {}
    if destination_exists:
        for name in RUNTIME_FILES:
            path = destination / name
            if path.is_symlink():
                raise CollectorInstallError(f"Installed {name} must not be a symlink")
            if path.exists() and not path.is_file():
                raise CollectorInstallError(f"Installed {name} is not a regular file")
            if path.exists():
                previous[name] = path.read_bytes()

    changed_names = tuple(name for name in RUNTIME_FILES if previous.get(name) != files[name])
    if not changed_names:
        return {
            "status": "unchanged",
            "destination": str(destination.resolve()),
            "version": version,
            "backup_path": None,
            "files": [],
        }

    existing_changed = tuple(name for name in changed_names if name in previous)
    backup_path: Path | None = None
    if existing_changed:
        selected_backup_root = (
            Path(backup_root).expanduser()
            if backup_root is not None
            else PROJECT_ROOT / ".dst-route-planner" / "collector-backups"
        )
        backup_path = _write_backup(selected_backup_root, previous, existing_changed)

    created_destination = not destination_exists
    destination_created_by_us = False
    install_succeeded = False
    stage: Path | None = None
    replaced: list[str] = []
    try:
        if created_destination:
            destination.mkdir()
            destination_created_by_us = True

        stage = Path(
            tempfile.mkdtemp(prefix=".dst-route-collector-stage-", dir=str(destination))
        )
        new_stage = stage / "new"
        old_stage = stage / "old"
        new_stage.mkdir()
        old_stage.mkdir()
        for name in changed_names:
            (new_stage / name).write_bytes(files[name])
            if name in previous:
                (old_stage / name).write_bytes(previous[name])

        for name in changed_names:
            os.replace(new_stage / name, destination / name)
            replaced.append(name)
        install_succeeded = True
    except OSError:
        if stage is not None:
            old_stage = stage / "old"
            for name in reversed(replaced):
                target = destination / name
                if name in previous:
                    try:
                        os.replace(old_stage / name, target)
                    except OSError:
                        try:
                            target.write_bytes(previous[name])
                        except OSError:
                            pass
                else:
                    try:
                        target.unlink()
                    except OSError:
                        pass
        raise
    finally:
        if stage is not None:
            _cleanup_stage(stage, changed_names)
        if destination_created_by_us and not install_succeeded:
            try:
                destination.rmdir()
            except OSError:
                pass

    return {
        "status": "updated" if destination_exists else "installed",
        "destination": str(destination.resolve()),
        "version": version,
        "backup_path": str(backup_path) if backup_path is not None else None,
        "files": list(changed_names),
    }
