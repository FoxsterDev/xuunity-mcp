from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from server_core import ToolInvocationError, read_json, write_json
from server_editor_host import (
    detect_unity_app_path_for_project,
    resolve_unity_app_version,
    resolve_unity_executable,
)
from server_host_platform import current_host_platform_adapter, is_wsl, wsl_to_windows_path


LICENSE_CAPABILITIES_CACHE_SCHEMA = 3
LICENSE_PROBE_DEFAULT_TIMEOUT_MS = 30000
BATCHMODE_SUPPORT_OVERRIDE_ENV = "XUUNITY_LIGHT_UNITY_MCP_BATCHMODE_SUPPORT_OVERRIDE"


def license_capabilities_cache_path(project_root: Path) -> Path:
    return project_root / "Library" / "XUUnityLightMcp" / "state" / "license_capabilities.json"


def default_license_probe_log_path(project_root: Path) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return project_root / "Library" / "XUUnityLightMcp" / "logs" / "license" / f"{timestamp}_batchmode_probe.log"


def classify_license_log(text: str, exit_code: int | None = None, timed_out: bool = False) -> dict[str, Any]:
    haystack = str(text or "")
    patterns: list[tuple[str, str]] = [
        (
            "no_valid_editor_license",
            r"No valid Unity Editor license found|Unity has not been activated with a valid License|No valid Unity license",
        ),
        (
            "access_token_unavailable",
            r"Access token is unavailable|access token.*unavailable|Hub.*access token",
        ),
        (
            "no_ulf_license",
            r"No ULF license found|No .*\.ulf .*license|Failed to load.*\.ulf",
        ),
        (
            "headless_entitlement_missing",
            r"headless.*entitlement|entitlement.*headless|Editor UI entitlement|UI entitlement|Build Server.*cannot.*Editor|not able to open the Unity Editor with a Build Server license",
        ),
        (
            "licensing_client_ipc_failure",
            r"Licensing Client.*IPC|LicensingClient.*IPC|IPC.*Licensing|licensing.*IPC|Failed to connect.*Licensing Client",
        ),
    ]
    for code, pattern in patterns:
        match = re.search(pattern, haystack, re.IGNORECASE)
        if match:
            if code == "access_token_unavailable" and access_token_warning_recovered(haystack, exit_code, timed_out):
                continue
            if code == "licensing_client_ipc_failure" and licensing_ipc_warning_recovered(haystack, exit_code, timed_out):
                continue
            return {
                "batchmode_blocker_code": code,
                "matched_pattern": pattern,
                "matched_text": _excerpt_around(haystack, match.start(), match.end()),
            }

    if timed_out:
        return {
            "batchmode_blocker_code": "unknown_batch_failure",
            "matched_pattern": "timeout",
            "matched_text": "Unity batchmode probe timed out.",
        }

    if exit_code is not None and int(exit_code) != 0:
        return {
            "batchmode_blocker_code": "unknown_batch_failure",
            "matched_pattern": "",
            "matched_text": first_non_empty_line(haystack),
        }

    return {
        "batchmode_blocker_code": "",
        "matched_pattern": "",
        "matched_text": "",
    }


def access_token_warning_recovered(text: str, exit_code: int | None, timed_out: bool) -> bool:
    if timed_out or exit_code is None or int(exit_code) != 0:
        return False
    success_patterns = (
        r"Successfully resolved entitlement details",
        r"Successfully updated license",
        r"\[Licensing::Module\] License group:",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in success_patterns)


def licensing_ipc_warning_recovered(text: str, exit_code: int | None, timed_out: bool) -> bool:
    if timed_out or exit_code is None or int(exit_code) != 0:
        return False
    success_patterns = (
        r"Successfully connected to LicensingClient",
        r"Connected to LicensingClient",
        r"Successfully connected to:\s+\"LicenseClient-",
        r"Exiting batchmode successfully",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in success_patterns)


def _excerpt_around(text: str, start: int, end: int, limit: int = 360) -> str:
    if not text:
        return ""
    left = max(0, start - limit // 2)
    right = min(len(text), end + limit // 2)
    excerpt = text[left:right].strip()
    if left > 0:
        excerpt = "..." + excerpt
    if right < len(text):
        excerpt += "..."
    return excerpt


def first_non_empty_line(text: str, limit: int = 320) -> str:
    for line in str(text or "").splitlines():
        candidate = line.strip()
        if candidate:
            return candidate[:limit]
    return ""


def build_license_capabilities(
    *,
    project_root: Path,
    unity_app: Path | str | None = None,
    refresh: bool = False,
    timeout_ms: int = LICENSE_PROBE_DEFAULT_TIMEOUT_MS,
) -> dict[str, Any]:
    resolved_unity_app = (
        detect_unity_app_path_for_project(project_root, str(unity_app))
        if unity_app
        else detect_unity_app_path_for_project(project_root, None)
    )
    unity_executable = resolve_unity_executable(resolved_unity_app)
    unity_version = resolve_unity_app_version(resolved_unity_app)
    cache_path = license_capabilities_cache_path(project_root)
    cache_key = {
        "unity_executable_path": str(unity_executable),
        "unity_version": unity_version,
    }

    override = parse_batchmode_support_override(os.environ.get(BATCHMODE_SUPPORT_OVERRIDE_ENV, ""))
    if override is not None:
        payload = build_capabilities_payload(
            project_root=project_root,
            unity_app=resolved_unity_app,
            unity_executable=unity_executable,
            unity_version=unity_version,
            cache_key=cache_key,
            probe_log_path=default_license_probe_log_path(project_root),
            batch_exit_code=None,
            timed_out=False,
            batchmode_supported=override["batchmode_supported"],
            blocker_code=str(override.get("batchmode_blocker_code") or ""),
            source_evidence=["environment_override"],
            from_cache=False,
            stderr="",
            stdout="",
            matched_text=str(override.get("matched_text") or ""),
        )
        payload["override_env"] = BATCHMODE_SUPPORT_OVERRIDE_ENV
        return payload

    if not refresh:
        cached = read_cached_license_capabilities(cache_path, cache_key)
        if cached is not None:
            cached["from_cache"] = True
            return cached

    timeout_ms = max(1000, int(timeout_ms or LICENSE_PROBE_DEFAULT_TIMEOUT_MS))
    probe_log_path = default_license_probe_log_path(project_root)
    probe_log_path.parent.mkdir(parents=True, exist_ok=True)
    project_path_str = wsl_to_windows_path(project_root) if is_wsl() else str(project_root)
    probe_log_path_str = wsl_to_windows_path(probe_log_path) if is_wsl() else str(probe_log_path)
    command = [
        str(unity_executable),
        "-batchmode",
        "-quit",
        "-projectPath",
        project_path_str,
        "-logFile",
        probe_log_path_str,
    ]

    stdout = ""
    stderr = ""
    batch_exit_code: int | None = None
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_ms / 1000.0,
        )
        batch_exit_code = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        batch_exit_code = 124
        stdout = exc.stdout.decode("utf-8", errors="ignore") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="ignore") if isinstance(exc.stderr, bytes) else str(exc.stderr or "")
    except OSError as exc:
        batch_exit_code = 127
        stderr = str(exc)

    log_text = ""
    if probe_log_path.is_file():
        try:
            log_text = probe_log_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            log_text = ""
    combined_text = "\n".join(part for part in (stdout, stderr, log_text) if part)
    classification = classify_license_log(combined_text, batch_exit_code, timed_out)
    blocker_code = str(classification.get("batchmode_blocker_code") or "")
    matched_text = str(classification.get("matched_text") or "")
    if batch_exit_code == 0 and not blocker_code and not timed_out:
        batchmode_supported: bool | None = True
    elif blocker_code and blocker_code != "unknown_batch_failure":
        batchmode_supported = False
    else:
        batchmode_supported = None

    source_evidence = ["unity_batch_probe"]
    if blocker_code:
        source_evidence.append(f"log_pattern:{blocker_code}")
    if batchmode_supported is None:
        source_evidence.append("batch_probe_inconclusive")

    payload = build_capabilities_payload(
        project_root=project_root,
        unity_app=resolved_unity_app,
        unity_executable=unity_executable,
        unity_version=unity_version,
        cache_key=cache_key,
        probe_log_path=probe_log_path,
        batch_exit_code=batch_exit_code,
        timed_out=timed_out,
        batchmode_supported=batchmode_supported,
        blocker_code=blocker_code,
        source_evidence=source_evidence,
        from_cache=False,
        stderr=stderr,
        stdout=stdout,
        matched_text=matched_text,
    )
    write_json(cache_path, payload)
    return payload


def build_capabilities_payload(
    *,
    project_root: Path,
    unity_app: Path,
    unity_executable: Path,
    unity_version: str,
    cache_key: dict[str, str],
    probe_log_path: Path,
    batch_exit_code: int | None,
    timed_out: bool,
    batchmode_supported: bool | None,
    blocker_code: str,
    source_evidence: list[str],
    from_cache: bool,
    stderr: str,
    stdout: str,
    matched_text: str,
) -> dict[str, Any]:
    editor_ui_supported = infer_editor_ui_supported(blocker_code)
    recommended_execution_lane = recommend_execution_lane(batchmode_supported, editor_ui_supported, blocker_code)
    return {
        "schema_version": LICENSE_CAPABILITIES_CACHE_SCHEMA,
        "action": "license_capabilities",
        "project_root": str(project_root),
        "unity_version": unity_version,
        "editor_path": str(unity_app),
        "unity_executable_path": str(unity_executable),
        "license_kind_inferred": infer_license_kind(blocker_code, batchmode_supported),
        "batchmode_supported": batchmode_supported,
        "editor_ui_supported": editor_ui_supported,
        "batchmode_blocker_code": blocker_code,
        "batchmode_probe_log_path": str(probe_log_path),
        "batchmode_probe_exit_code": batch_exit_code,
        "batchmode_probe_timed_out": bool(timed_out),
        "recommended_execution_lane": recommended_execution_lane,
        "source_evidence": source_evidence,
        "source_evidence_detail": {
            "matched_text": matched_text[:1000],
            "stderr": (stderr or "")[:1000],
            "stdout": (stdout or "")[:1000],
            "platform_kind": current_host_platform_adapter().platform_kind,
        },
        "cache_key": cache_key,
        "cache_path": str(license_capabilities_cache_path(project_root)),
        "from_cache": from_cache,
        "probed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def infer_editor_ui_supported(blocker_code: str) -> bool | None:
    if blocker_code == "headless_entitlement_missing":
        return False
    return None


def recommend_execution_lane(
    batchmode_supported: bool | None,
    editor_ui_supported: bool | None,
    blocker_code: str,
) -> str:
    if batchmode_supported is True:
        return "batch"
    if editor_ui_supported is False:
        return "none"
    if batchmode_supported is False:
        return "gui"
    if blocker_code == "unknown_batch_failure":
        return "batch_diagnostic_required"
    return "unknown"


def infer_license_kind(blocker_code: str, batchmode_supported: bool | None) -> str:
    if batchmode_supported is True:
        return "batch_capable"
    if blocker_code == "headless_entitlement_missing":
        return "headless_or_build_server_related"
    if blocker_code in {"access_token_unavailable", "no_ulf_license", "no_valid_editor_license"}:
        return "interactive_or_hub_activation_required"
    if blocker_code:
        return "unknown_license_or_host_blocker"
    return "unknown"


def read_cached_license_capabilities(cache_path: Path, cache_key: dict[str, str]) -> dict[str, Any] | None:
    if not cache_path.is_file():
        return None
    try:
        payload = read_json(cache_path)
    except (OSError, json.JSONDecodeError, ToolInvocationError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("schema_version") or 0) != LICENSE_CAPABILITIES_CACHE_SCHEMA:
        return None
    cached_key = payload.get("cache_key")
    if not isinstance(cached_key, dict):
        return None
    if str(cached_key.get("unity_executable_path") or "") != cache_key["unity_executable_path"]:
        return None
    if str(cached_key.get("unity_version") or "") != cache_key["unity_version"]:
        return None
    return dict(payload)


def parse_batchmode_support_override(raw_value: str) -> dict[str, Any] | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"supported", "true", "1", "batch"}:
        return {
            "batchmode_supported": True,
            "batchmode_blocker_code": "",
            "matched_text": "",
        }
    if lowered in {"unknown", "null", "inconclusive"}:
        return {
            "batchmode_supported": None,
            "batchmode_blocker_code": "unknown_batch_failure",
            "matched_text": "Batchmode support forced to unknown by environment override.",
        }
    if ":" in text:
        state, code = text.split(":", 1)
        state = state.strip().lower()
        code = code.strip() or "unknown_batch_failure"
        if state in {"unsupported", "false", "0", "gui"}:
            return {
                "batchmode_supported": False,
                "batchmode_blocker_code": code,
                "matched_text": "Batchmode support forced to unsupported by environment override.",
            }
    if lowered in {"unsupported", "false", "0", "gui"}:
        return {
            "batchmode_supported": False,
            "batchmode_blocker_code": "no_valid_editor_license",
            "matched_text": "Batchmode support forced to unsupported by environment override.",
        }
    return None
