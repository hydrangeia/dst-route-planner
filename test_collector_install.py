from pathlib import Path

import pytest

import dst_route_planner.collector_install as collector_install


RUNTIME_FILES = ("collector.lua", "modmain.lua", "modinfo.lua")


def _write_bundle(directory: Path, *, version: str = "0.5.0", marker: str = "old") -> dict[str, bytes]:
    directory.mkdir(parents=True, exist_ok=True)
    files = {
        "collector.lua": f"collector {marker}\n".encode(),
        "modmain.lua": f"modmain {marker}\n".encode(),
        "modinfo.lua": f'name = "test collector"\nversion = "{version}"\n'.encode(),
    }
    for name, content in files.items():
        (directory / name).write_bytes(content)
    return files


@pytest.fixture
def bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = tmp_path / "bundle source"
    _write_bundle(source)
    monkeypatch.setattr(collector_install, "SOURCE_DIR", source)
    return source


def _mods(tmp_path: Path) -> Path:
    mods = tmp_path / "世界 存档" / "mods"
    mods.mkdir(parents=True)
    return mods


def test_fresh_install_uses_only_bundled_runtime_files(bundle: Path, tmp_path: Path) -> None:
    mods = _mods(tmp_path)

    result = collector_install.install_collector(mods)

    destination = mods / "dst_route_collector"
    assert result == {
        "status": "installed",
        "destination": str(destination.resolve()),
        "version": "0.5.0",
        "backup_path": None,
        "files": list(RUNTIME_FILES),
    }
    assert {name for name in destination.iterdir()} == {
        destination / name for name in RUNTIME_FILES
    }
    assert not (tmp_path / ".dst-route-planner" / "collector-backups").exists()


def test_identical_install_is_a_noop_and_does_not_create_backups(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mods = _mods(tmp_path)
    first = collector_install.install_collector(mods)
    destination = Path(first["destination"])
    before = {name: (destination / name).read_bytes() for name in RUNTIME_FILES}
    backup_root = tmp_path / "backup root"

    def unexpected_replace(*_args: object) -> None:
        raise AssertionError("unchanged install must not replace files")

    monkeypatch.setattr(collector_install.os, "replace", unexpected_replace)
    second = collector_install.install_collector(mods, backup_root=backup_root)

    assert second["status"] == "unchanged"
    assert second["files"] == []
    assert second["backup_path"] is None
    assert not backup_root.exists()
    assert {name: (destination / name).read_bytes() for name in RUNTIME_FILES} == before


def test_update_backs_up_changed_runtime_files_and_keeps_unknown_files(
    bundle: Path, tmp_path: Path
) -> None:
    mods = _mods(tmp_path)
    initial = collector_install.install_collector(mods)
    destination = Path(initial["destination"])
    old = {name: (destination / name).read_bytes() for name in RUNTIME_FILES}
    (destination / "user-notes.txt").write_text("keep me", encoding="utf-8")
    new = _write_bundle(bundle, version="0.5.1", marker="new")
    backup_root = tmp_path / "备份 文件"

    result = collector_install.install_collector(mods, backup_root=backup_root)

    assert result["status"] == "updated"
    assert result["version"] == "0.5.1"
    assert result["files"] == list(RUNTIME_FILES)
    backup = Path(result["backup_path"])
    assert backup.is_absolute()
    assert {path.name for path in backup.iterdir()} == set(RUNTIME_FILES)
    assert {name: (backup / name).read_bytes() for name in RUNTIME_FILES} == old
    assert {name: (destination / name).read_bytes() for name in RUNTIME_FILES} == new
    assert (destination / "user-notes.txt").read_text(encoding="utf-8") == "keep me"


def test_invalid_or_missing_mods_folder_is_rejected(bundle: Path, tmp_path: Path) -> None:
    with pytest.raises(collector_install.CollectorInstallError, match="does not exist"):
        collector_install.install_collector(tmp_path / "missing" / "mods")

    wrong_name = tmp_path / "not-mods"
    wrong_name.mkdir()
    with pytest.raises(collector_install.CollectorInstallError, match="mods folder"):
        collector_install.install_collector(wrong_name)


def test_missing_bundle_file_and_invalid_version_fail_before_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mods = _mods(tmp_path)
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "collector.lua").write_text("local x = 1", encoding="utf-8")
    monkeypatch.setattr(collector_install, "SOURCE_DIR", incomplete)
    with pytest.raises(collector_install.CollectorInstallError, match="modmain.lua"):
        collector_install.install_collector(mods)
    assert not (mods / "dst_route_collector").exists()

    malformed = tmp_path / "malformed"
    _write_bundle(malformed)
    (malformed / "modinfo.lua").write_text('name = "x"\n', encoding="utf-8")
    monkeypatch.setattr(collector_install, "SOURCE_DIR", malformed)
    with pytest.raises(collector_install.CollectorInstallError, match="version"):
        collector_install.install_collector(mods)
    assert not (mods / "dst_route_collector").exists()


def test_source_and_destination_overlap_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mods = _mods(tmp_path)
    destination = mods / "dst_route_collector"
    _write_bundle(destination)
    monkeypatch.setattr(collector_install, "SOURCE_DIR", destination)

    with pytest.raises(collector_install.CollectorInstallError, match="overlap"):
        collector_install.install_collector(mods)

    nested_source = destination / "nested source"
    _write_bundle(nested_source)
    monkeypatch.setattr(collector_install, "SOURCE_DIR", nested_source)
    with pytest.raises(collector_install.CollectorInstallError, match="overlap"):
        collector_install.install_collector(mods)


def test_destination_resolving_outside_selected_mods_is_rejected(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mods = _mods(tmp_path)
    destination = mods / "dst_route_collector"
    redirected = tmp_path / "outside" / "dst_route_collector"
    real_resolve = Path.resolve

    def redirect_destination(path: Path, strict: bool = False) -> Path:
        if path == destination:
            return redirected
        return real_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", redirect_destination)
    with pytest.raises(collector_install.CollectorInstallError, match="outside"):
        collector_install.install_collector(mods)
    assert not destination.exists()


def test_destination_and_runtime_symlinks_are_rejected(
    bundle: Path, tmp_path: Path
) -> None:
    mods = _mods(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = mods / "dst_route_collector"
    try:
        destination.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable")

    with pytest.raises(collector_install.CollectorInstallError, match="symlink"):
        collector_install.install_collector(mods)

    destination.unlink()
    destination.mkdir()
    target = tmp_path / "outside.lua"
    target.write_text("keep", encoding="utf-8")
    try:
        (destination / "collector.lua").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("file symlinks are unavailable")
    with pytest.raises(collector_install.CollectorInstallError, match="collector.lua"):
        collector_install.install_collector(mods)
    assert target.read_text(encoding="utf-8") == "keep"


def test_backup_failure_leaves_installed_runtime_untouched(
    bundle: Path, tmp_path: Path
) -> None:
    mods = _mods(tmp_path)
    first = collector_install.install_collector(mods)
    destination = Path(first["destination"])
    before = {name: (destination / name).read_bytes() for name in RUNTIME_FILES}
    _write_bundle(bundle, version="0.5.1", marker="updated")
    backup_root_file = tmp_path / "backup-root-file"
    backup_root_file.write_text("block backup directory", encoding="utf-8")

    with pytest.raises(OSError):
        collector_install.install_collector(mods, backup_root=backup_root_file)

    assert {name: (destination / name).read_bytes() for name in RUNTIME_FILES} == before


def test_staging_write_failure_cleans_fresh_destination(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mods = _mods(tmp_path)
    real_write_bytes = Path.write_bytes

    def fail_staged_write(path: Path, content: bytes) -> int:
        if path.parent.name == "new":
            raise OSError("injected staging write failure")
        return real_write_bytes(path, content)

    monkeypatch.setattr(Path, "write_bytes", fail_staged_write)
    with pytest.raises(OSError, match="staging write"):
        collector_install.install_collector(mods)

    destination = mods / "dst_route_collector"
    assert not destination.exists()
    assert not list(mods.glob(".dst-route-collector-stage-*"))


def test_failed_later_replace_rolls_back_earlier_replacements(
    bundle: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mods = _mods(tmp_path)
    first = collector_install.install_collector(mods)
    destination = Path(first["destination"])
    before = {name: (destination / name).read_bytes() for name in RUNTIME_FILES}
    _write_bundle(bundle, version="0.5.1", marker="updated")

    real_replace = collector_install.os.replace
    staged_replacements = 0

    def fail_second_stage_replace(source: Path, target: Path) -> None:
        nonlocal staged_replacements
        if Path(source).parent.name == "new":
            staged_replacements += 1
            if staged_replacements == 2:
                raise OSError("injected replacement failure")
        real_replace(source, target)

    monkeypatch.setattr(collector_install.os, "replace", fail_second_stage_replace)
    with pytest.raises(OSError, match="injected"):
        collector_install.install_collector(mods, backup_root=tmp_path / "backups")

    assert {name: (destination / name).read_bytes() for name in RUNTIME_FILES} == before
    assert not list(destination.glob(".dst-route-collector-stage-*"))
