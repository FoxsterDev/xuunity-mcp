from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterator

from server_core import parse_utc_timestamp, write_json

EDITOR_INPUT_EXTENSIONS = frozenset({".cs", ".asmdef", ".asmref", ".rsp"})
EDITOR_INPUT_SNAPSHOT_FILE_NAME = "editor_input_snapshot.json"
CHANGED_PATH_LIMIT = 8
HOST_BATCH_PROBE_TRIGGER = "host_batch_probe"
SNAPSHOT_COMPILE_ERROR_LINE_LIMIT = 8
FNV_OFFSET_BASIS = 14695981039346656037
FNV_PRIME = 1099511628211
FNV_MASK = (1 << 64) - 1


def editor_input_snapshot_path(project_root: Path) -> Path:
    return project_root / "Library" / "XUUnityLightMcp" / "state" / EDITOR_INPUT_SNAPSHOT_FILE_NAME


def is_unity_ignored_entry_name(name: str) -> bool:
    if not name:
        return False
    if name[0] == "." or name[-1] == "~":
        return True
    return name.lower() == "cvs"


def _local_package_paths(manifest_path: Path) -> list[str]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    dependencies = manifest.get("dependencies") if isinstance(manifest, dict) else None
    paths: list[str] = []
    for value in (dependencies or {}).values() if isinstance(dependencies, dict) else []:
        text = str(value or "")
        if not text.startswith("file:"):
            continue
        local = text[len("file:"):]
        if local.lower().endswith((".tgz", ".tar.gz")):
            continue
        paths.append(local)
    return paths


def resolve_editor_input_roots(project_root: Path) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()

    def add(root: Path) -> None:
        full = os.path.normpath(os.path.abspath(str(root)))
        if full.lower() not in seen:
            seen.add(full.lower())
            roots.append(Path(full))

    assets = project_root / "Assets"
    if assets.is_dir():
        roots.append(assets)
        seen.add(os.path.normpath(os.path.abspath(str(assets))).lower())
    packages = project_root / "Packages"
    if not packages.is_dir():
        return roots
    try:
        children = sorted(packages.iterdir())
    except OSError:
        children = []
    for child in children:
        if child.is_dir() and not is_unity_ignored_entry_name(child.name) and (child / "package.json").is_file():
            add(child)
    for local in _local_package_paths(packages / "manifest.json"):
        candidate = Path(local) if os.path.isabs(local) else packages / local
        if candidate.is_dir() and (candidate / "package.json").is_file():
            add(candidate)
    return roots


def iter_editor_inputs(roots: list[Path]) -> Iterator[Path]:
    pending = [str(root) for root in roots]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            if is_unity_ignored_entry_name(entry.name):
                continue
            try:
                if entry.is_dir():
                    pending.append(entry.path)
                elif entry.is_file() and os.path.splitext(entry.name)[1].lower() in EDITOR_INPUT_EXTENSIONS:
                    yield Path(entry.path)
            except OSError:
                continue


def editor_input_key(project_root: Path, path: Path) -> str:
    root_text = str(project_root).rstrip("/\\")
    path_text = str(path)
    prefix = root_text + os.sep
    if path_text.lower().startswith(prefix.lower()):
        path_text = path_text[len(prefix):]
    return path_text.replace("\\", "/")


def hash_editor_input(path: Path) -> str:
    value = FNV_OFFSET_BASIS
    length = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            length += len(chunk)
            for byte in chunk:
                value = ((value ^ byte) * FNV_PRIME) & FNV_MASK
    return f"{length}:{value:016x}"


def read_persisted_editor_input_snapshot(project_root: Path) -> dict[str, Any] | None:
    path = editor_input_snapshot_path(project_root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    paths = raw.get("paths")
    hashes = raw.get("hashes")
    if not isinstance(paths, list) or not isinstance(hashes, list) or len(paths) != len(hashes):
        return None
    if parse_utc_timestamp(raw.get("basis_utc")) is None:
        return None
    return raw


def newest_editor_input_after(project_root: Path, since_epoch: float) -> tuple[str, int]:
    newest_key = ""
    newest_mtime = since_epoch
    count = 0
    for path in iter_editor_inputs(resolve_editor_input_roots(project_root)):
        count += 1
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        if modified > newest_mtime:
            newest_mtime = modified
            newest_key = editor_input_key(project_root, path)
    return newest_key, count


def compare_editor_inputs_with_snapshot(project_root: Path) -> dict[str, Any]:
    snapshot_path = editor_input_snapshot_path(project_root)
    result: dict[str, Any] = {
        "state": "unavailable",
        "snapshot_path": str(snapshot_path),
        "input_count": 0,
        "changed_count": 0,
        "changed_paths": [],
    }
    snapshot = read_persisted_editor_input_snapshot(project_root)
    if snapshot is None:
        result["reason"] = "snapshot_missing_or_unreadable" if snapshot_path.exists() else "snapshot_missing"
        return result

    basis = float(parse_utc_timestamp(snapshot.get("basis_utc")) or 0.0)
    compiled = {str(key): str(value) for key, value in zip(snapshot["paths"], snapshot["hashes"])}
    dirty = {str(item) for item in snapshot.get("dirty_at_capture") or []}
    changed: list[str] = []
    seen: set[str] = set()
    input_count = 0
    for path in iter_editor_inputs(resolve_editor_input_roots(project_root)):
        input_count += 1
        key = editor_input_key(project_root, path)
        seen.add(key)
        compiled_hash = compiled.get(key)
        if compiled_hash is None or key in dirty:
            changed.append(key)
            continue
        try:
            if path.stat().st_mtime <= basis:
                continue
            if hash_editor_input(path) != compiled_hash:
                changed.append(key)
        except OSError:
            changed.append(key)
    changed.extend(sorted(key for key in compiled if key not in seen))

    result.update(
        {
            "state": "ready",
            "input_count": input_count,
            "changed_count": len(changed),
            "changed_paths": changed[:CHANGED_PATH_LIMIT],
            "basis_utc": str(snapshot.get("basis_utc") or ""),
            "snapshot_trigger": str(snapshot.get("trigger") or ""),
            "snapshot_captured_utc": str(snapshot.get("captured_utc") or ""),
            "snapshot_compile_outcome": str(snapshot.get("compile_outcome") or "unknown"),
            "snapshot_compile_error_count": int(snapshot.get("compile_error_count") or 0),
            "snapshot_compile_error_lines": [
                str(line) for line in snapshot.get("compile_error_lines") or [] if isinstance(line, str)
            ][:SNAPSHOT_COMPILE_ERROR_LINE_LIMIT],
        }
    )
    return result


def project_has_compiled_before(project_root: Path) -> bool:
    return (project_root / "Library" / "ScriptAssemblies").is_dir()


def _snapshot_utc(epoch: float) -> str:
    whole = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch))
    return f"{whole}.{int((epoch % 1) * 10_000_000):07d}Z"


def write_host_probe_red_snapshot(
    project_root: Path,
    *,
    probe_started_epoch: float,
    compile_error_count: int,
    compile_error_lines: list[str],
) -> dict[str, Any]:
    """Record a red batch probe: Unity loads no domain on red code, so the editor never refreshes the snapshot."""
    paths: list[str] = []
    hashes: list[str] = []
    dirty: list[str] = []
    for path in iter_editor_inputs(resolve_editor_input_roots(project_root)):
        try:
            digest = hash_editor_input(path)
            modified = path.stat().st_mtime
        except OSError:
            continue
        key = editor_input_key(project_root, path)
        paths.append(key)
        hashes.append(digest)
        if modified > probe_started_epoch:
            # Edited while the probe ran: the red verdict does not cover this content.
            dirty.append(key)
    snapshot_path = editor_input_snapshot_path(project_root)
    write_json(
        snapshot_path,
        {
            "schema_version": 1,
            "trigger": HOST_BATCH_PROBE_TRIGGER,
            "basis_utc": _snapshot_utc(probe_started_epoch),
            "captured_utc": _snapshot_utc(time.time()),
            "editor_pid": 0,
            "compile_outcome": "failed",
            "compile_error_count": max(1, int(compile_error_count or 0)),
            "input_count": len(paths),
            "paths": paths,
            "hashes": hashes,
            "dirty_at_capture": dirty,
            "compile_error_lines": [str(line) for line in compile_error_lines][:SNAPSHOT_COMPILE_ERROR_LINE_LIMIT],
        },
    )
    return {
        "written": True,
        "snapshot_path": str(snapshot_path),
        "trigger": HOST_BATCH_PROBE_TRIGGER,
        "input_count": len(paths),
        "dirty_at_capture_count": len(dirty),
    }


def editor_open_compile_preflight_decision(project_root: Path) -> dict[str, Any]:
    comparison = compare_editor_inputs_with_snapshot(project_root)
    decision: dict[str, Any] = {"input_comparison": comparison, "run_compile_probe": False}
    if comparison["state"] != "ready":
        if project_has_compiled_before(project_root):
            # No snapshot yet (first open after a package upgrade): the last compile outcome is unknown.
            decision["run_compile_probe"] = True
            decision["reason"] = "input_snapshot_missing_compile_outcome_unknown"
        else:
            decision["reason"] = "input_snapshot_unavailable"
    elif comparison["changed_count"] > 0:
        decision["run_compile_probe"] = True
        decision["reason"] = "editor_inputs_changed_since_last_compile"
    elif comparison.get("snapshot_compile_outcome") == "failed":
        if comparison.get("snapshot_trigger") == HOST_BATCH_PROBE_TRIGGER:
            decision["recorded_red"] = True
            decision["reason"] = "compile_red_recorded_by_host_probe_inputs_unchanged"
        else:
            decision["run_compile_probe"] = True
            decision["reason"] = "last_recorded_compile_failed"
    else:
        decision["reason"] = "editor_inputs_unchanged_since_last_compile"
    return decision


__all__ = [name for name in globals() if not name.startswith("__")]
