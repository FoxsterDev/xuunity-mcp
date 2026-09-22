"""Offline validation-acceptance evaluator.

Joins an owner-approved validation plan with evidence receipts and reports a
deterministic acceptance verdict that keeps the full required denominator.
Read-only except for the report the caller asks for: it never launches Unity,
fetches URLs, or executes recovery commands.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

from server_core import read_json  # noqa: E402

PLAN_SCHEMA_VERSION = "xuunity.light-mcp.validation-plan.v1"
RECEIPTS_SCHEMA_VERSION = "xuunity.light-mcp.validation-receipts.v1"
ACCEPTANCE_SCHEMA_VERSION = "xuunity.light-mcp.validation-acceptance.v1"
CONSUMER_VERDICT_SCHEMA_VERSION = "foxsterlabs.ccp.release-verdict.v2"
EVALUATOR_VERSION = "0.1.0"
SCHEMA_ID_BASE = "https://github.com/FoxsterDev/xuunity-mcp/templates/workflows/"

MAX_INPUT_BYTES = 10 * 1024 * 1024
MAX_ITEMS = 10_000
COMPACT_REASON_ROWS = 5
COMPACT_DETAIL_CHARS = 200

STAGES = (
    "static",
    "resolve",
    "compile",
    "editmode",
    "playmode",
    "build",
    "export",
    "player-runtime",
    "device-runtime",
    "client-integration",
)
TEST_STAGES = ("editmode", "playmode")
CHANNELS = ("native-mcp", "helper-cli", "direct-unity", "any")
LANES = ("batch", "gui", "none")
OPERATION_OUTCOMES = ("passed", "failed", "blocked", "not_run")
ROW_OUTCOMES = ("pass", "fail", "blocked", "not_run")
VERDICTS = ("pass", "fail", "blocked", "partial")
DIAGNOSTICS_SCOPES = ("all", "package")
EVIDENCE_KINDS = ("raw", "helper_response")
DIMENSION_KEYS = ("unityVersion", "target", "scriptingBackend", "inputMode")

REASON_CODES = (
    "receipt_missing",
    "receipt_conflict",
    "source_identity_mismatch",
    "dimension_mismatch",
    "scene_mismatch",
    "stage_mismatch",
    "channel_unverified",
    "evidence_missing",
    "evidence_changed",
    "evidence_outside_roots",
    "evidence_undecodable",
    "operation_failed",
    "capability_unavailable",
    "test_verdict_not_passed",
    "test_count_insufficient",
    "runtime_timeout",
    "post_settle_errors",
    "semantic_assertion_failed",
    "diagnostics_unmeasured",
    "warning_budget_exceeded",
    "rebuild_unmeasured",
    "rebuild_cached_only",
    "artifact_missing",
    "artifact_changed",
    "evaluation_invalid",
)

HELPER_STAGE_BY_PAYLOAD_TYPE = {
    "unity.compile.player_scripts": "compile",
    "unity.tests.run_editmode": "editmode",
    "unity.tests.run_playmode": "playmode",
}


class ValidationInputError(ValueError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


# --- strict specs (single source for the validator and the JSON schema files) -----------------

SOURCE_IDENTITY_SPEC: dict[str, Any] = {
    "required": {"algorithm": ("enum", ("sha256",)), "digest": "str"},
    "optional": {"manifestRef": "str?", "dirtyPaths": ("list?", "str"), "commit": "str?"},
}
DIMENSIONS_SPEC: dict[str, Any] = {"required": {key: "str?" for key in DIMENSION_KEYS}, "optional": {}}
POLICY_SPEC: dict[str, Any] = {
    "required": {},
    "optional": {
        "warningBudget": "int?",
        "diagnosticsScope": ("enum", DIAGNOSTICS_SCOPES),
        "requireMeasuredRebuild": "bool",
        "minTests": "int?",
        "semanticAssertions": ("list", "str"),
    },
}
REQUIREMENT_SPEC: dict[str, Any] = {
    "required": {
        "id": "str",
        "required": "bool",
        "stage": ("enum", STAGES),
        "executionChannel": ("enum", CHANNELS),
        "dimensions": ("object", DIMENSIONS_SPEC),
        "scene": "str?",
        "artifactRequired": "bool",
    },
    "optional": {
        "executionLane": ("enum?", LANES),
        "policy": ("object", POLICY_SPEC),
        "receiptId": "str?",
        "description": "str",
    },
}
PLAN_SPEC: dict[str, Any] = {
    "required": {
        "schemaVersion": ("enum", (PLAN_SCHEMA_VERSION,)),
        "planId": "str",
        "projectId": "str",
        "sourceIdentity": ("object", SOURCE_IDENTITY_SPEC),
        "requirements": ("list", ("object", REQUIREMENT_SPEC)),
    },
    "optional": {"runId": "str?", "evidenceRoots": ("list", "str"), "description": "str"},
}
REF_SPEC: dict[str, Any] = {"required": {"path": "str", "sha256": "str"}, "optional": {}}
PRODUCER_SPEC: dict[str, Any] = {"required": {"name": "str", "version": "str?", "route": "str?"}, "optional": {}}
DIAGNOSTICS_SPEC: dict[str, Any] = {
    "required": {"scope": ("enum", DIAGNOSTICS_SCOPES), "complete": "bool"},
    "optional": {"warningCount": "int?", "uniqueWarningCount": "int?", "truncated": "bool?", "samples": ("list", "str")},
}
REBUILD_SPEC: dict[str, Any] = {
    "required": {"status": "str?"},
    "optional": {"rebuiltAssemblyCount": "int?", "cachedAssemblyCount": "int?"},
}
TESTS_SPEC: dict[str, Any] = {
    "required": {"verdict": "str?"},
    "optional": {"total": "int?", "passed": "int?", "failed": "int?", "skipped": "int?", "postSettleErrorCount": "int?"},
}
ASSERTION_SPEC: dict[str, Any] = {"required": {"name": "str", "passed": "bool"}, "optional": {"detail": "str?"}}
BLOCKER_SPEC: dict[str, Any] = {"required": {"code": "str"}, "optional": {"message": "str?"}}
RECEIPT_SPEC: dict[str, Any] = {
    "required": {
        "receiptId": "str",
        "requirementId": "str",
        "sourceIdentity": ("object", SOURCE_IDENTITY_SPEC),
        "dimensions": ("object", DIMENSIONS_SPEC),
        "stage": ("enum", STAGES),
        "executionChannel": ("enum", CHANNELS),
        "evidenceRef": ("object", REF_SPEC),
    },
    "optional": {
        "evidenceKind": ("enum", EVIDENCE_KINDS),
        "producer": ("object", PRODUCER_SPEC),
        "startedAt": "str?",
        "completedAt": "str?",
        "operationOutcome": ("enum", OPERATION_OUTCOMES),
        "executionLane": ("enum?", LANES),
        "requestId": "str?",
        "clientReceiptRef": ("object?", REF_SPEC),
        "clientKind": "str?",
        "scene": "str?",
        "artifact": ("object?", REF_SPEC),
        "diagnostics": ("object?", DIAGNOSTICS_SPEC),
        "rebuild": ("object?", REBUILD_SPEC),
        "tests": ("object?", TESTS_SPEC),
        "semanticAssertions": ("list?", ("object", ASSERTION_SPEC)),
        "executionBlocker": ("object?", BLOCKER_SPEC),
        "reused": "bool",
        "originalRunAt": "str?",
        "supersedes": ("list", "str"),
        "notes": "str?",
    },
}
RECEIPTS_SPEC: dict[str, Any] = {
    "required": {
        "schemaVersion": ("enum", (RECEIPTS_SCHEMA_VERSION,)),
        "receipts": ("list", ("object", RECEIPT_SPEC)),
    },
    "optional": {},
}
COUNTS_SPEC: dict[str, Any] = {
    "required": {"total": "int", "pass": "int", "fail": "int", "blocked": "int", "not_run": "int"},
    "optional": {},
}
PROVENANCE_SPEC: dict[str, Any] = {
    "required": {},
    "optional": {
        "evidenceRef": ("object?", REF_SPEC),
        "evidenceKind": ("enum?", EVIDENCE_KINDS),
        "producer": ("object?", PRODUCER_SPEC),
        "requestId": "str?",
        "fieldPaths": ("list", "str"),
    },
}
ROW_SPEC: dict[str, Any] = {
    "required": {
        "requirementId": "str",
        "required": "bool",
        "stage": ("enum", STAGES),
        "executionChannel": ("enum", CHANNELS),
        "dimensions": ("object", DIMENSIONS_SPEC),
        "scene": "str?",
        "matchedReceiptIds": ("list", "str"),
        "operationOutcome": ("enum?", OPERATION_OUTCOMES),
        "outcome": ("enum", ROW_OUTCOMES),
        "reused": "bool",
        "originalRunAt": "str?",
        "reasons": ("list", "str"),
        "details": ("list", "str"),
    },
    "optional": {"policy": ("object", POLICY_SPEC), "provenance": ("object", PROVENANCE_SPEC)},
}
ACCEPTANCE_SPEC: dict[str, Any] = {
    "required": {
        "schemaVersion": ("enum", (ACCEPTANCE_SCHEMA_VERSION,)),
        "evaluatorVersion": "str",
        "planId": "str",
        "planSha256": "str",
        "projectId": "str",
        "sourceIdentity": ("object", SOURCE_IDENTITY_SPEC),
        "verdict": ("enum", VERDICTS),
        "required": ("object", COUNTS_SPEC),
        "optional": ("object", COUNTS_SPEC),
        "reusedCount": "int",
        "rows": ("list", ("object", ROW_SPEC)),
        "validationGaps": ("list", "str"),
        "reportRef": ("object", {"required": {"path": "str"}, "optional": {}}),
    },
    "optional": {"runId": "str?", "generatedAt": "str?"},
}

SCHEMA_DOCUMENTS = {
    "validation_plan.schema.json": ("XUUnity Light Unity MCP Validation Plan", PLAN_SPEC),
    "validation_receipts.schema.json": ("XUUnity Light Unity MCP Validation Receipts", RECEIPTS_SPEC),
    "validation_acceptance.schema.json": ("XUUnity Light Unity MCP Validation Acceptance Report", ACCEPTANCE_SPEC),
}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_value(value: Any, type_spec: Any, path: str) -> None:
    if isinstance(type_spec, str):
        nullable = type_spec.endswith("?")
        base = type_spec.rstrip("?")
        if value is None:
            if nullable:
                return
            raise ValidationInputError("schema_violation", f"{path}: null is not allowed")
        ok = {"str": lambda v: isinstance(v, str), "int": _is_int, "bool": lambda v: isinstance(v, bool)}[base](value)
        if not ok:
            raise ValidationInputError("schema_violation", f"{path}: expected {base}")
        if base == "str" and not value.strip() and not nullable:
            raise ValidationInputError("schema_violation", f"{path}: string must be nonempty")
        return
    kind, inner = type_spec
    nullable = kind.endswith("?")
    kind = kind.rstrip("?")
    if value is None:
        if nullable:
            return
        raise ValidationInputError("schema_violation", f"{path}: null is not allowed")
    if kind == "enum":
        if value not in inner:
            raise ValidationInputError("schema_violation", f"{path}: {value!r} is not one of {list(inner)}")
        return
    if kind == "list":
        if not isinstance(value, list):
            raise ValidationInputError("schema_violation", f"{path}: expected array")
        if len(value) > MAX_ITEMS:
            raise ValidationInputError("input_too_large", f"{path}: more than {MAX_ITEMS} items")
        for index, item in enumerate(value):
            _validate_value(item, inner, f"{path}[{index}]")
        return
    if kind == "object":
        _validate_object(value, inner, path)
        return
    raise AssertionError(f"unknown spec kind {kind}")


def _validate_object(value: Any, spec: dict[str, Any], path: str) -> None:
    if not isinstance(value, dict):
        raise ValidationInputError("schema_violation", f"{path}: expected object")
    allowed = set(spec["required"]) | set(spec["optional"])
    unknown = sorted(key for key in value if key not in allowed)
    if unknown:
        raise ValidationInputError("schema_violation", f"{path}: unknown keys {unknown}")
    missing = [key for key in spec["required"] if key not in value]
    if missing:
        raise ValidationInputError("schema_violation", f"{path}: missing required keys {missing}")
    for key, type_spec in spec["required"].items():
        _validate_value(value[key], type_spec, f"{path}.{key}")
    for key, type_spec in spec["optional"].items():
        if key in value:
            _validate_value(value[key], type_spec, f"{path}.{key}")


def _unique_ids(items: list[dict[str, Any]], key: str, path: str) -> None:
    seen: set[str] = set()
    for item in items:
        identifier = item[key]
        if identifier in seen:
            raise ValidationInputError("duplicate_id", f"{path}: duplicate {key} {identifier!r}")
        seen.add(identifier)


def validate_plan(plan: Any) -> None:
    if isinstance(plan, dict) and plan.get("schemaVersion") != PLAN_SCHEMA_VERSION:
        raise ValidationInputError("unknown_schema_version", f"plan.schemaVersion {plan.get('schemaVersion')!r} is not supported")
    _validate_object(plan, PLAN_SPEC, "plan")
    if not plan["requirements"]:
        raise ValidationInputError("schema_violation", "plan.requirements must be nonempty")
    _unique_ids(plan["requirements"], "id", "plan.requirements")


def validate_receipts(document: Any) -> None:
    if isinstance(document, dict) and document.get("schemaVersion") != RECEIPTS_SCHEMA_VERSION:
        raise ValidationInputError(
            "unknown_schema_version", f"receipts.schemaVersion {document.get('schemaVersion')!r} is not supported"
        )
    _validate_object(document, RECEIPTS_SPEC, "receipts")
    _unique_ids(document["receipts"], "receiptId", "receipts.receipts")
    for index, receipt in enumerate(document["receipts"]):
        if receipt.get("evidenceKind", "raw") == "helper_response":
            continue
        missing = [key for key in ("producer", "startedAt", "completedAt", "operationOutcome") if key not in receipt]
        if missing:
            raise ValidationInputError(
                "schema_violation",
                f"receipts.receipts[{index}]: raw receipts must carry {missing}",
            )


def validate_acceptance_report(report: Any) -> None:
    _validate_object(report, ACCEPTANCE_SPEC, "report")


# --- JSON schema documents generated from the specs --------------------------------------------

def _schema_for(type_spec: Any) -> dict[str, Any]:
    if isinstance(type_spec, str):
        base = {"str": "string", "int": "integer", "bool": "boolean"}[type_spec.rstrip("?")]
        return {"type": [base, "null"] if type_spec.endswith("?") else base}
    kind, inner = type_spec
    nullable = kind.endswith("?")
    kind = kind.rstrip("?")
    if kind == "enum":
        values = list(inner) + ([None] if nullable else [])
        return {"enum": values}
    if kind == "list":
        return {"type": ["array", "null"] if nullable else "array", "items": _schema_for(inner)}
    if kind == "object":
        document = _object_schema(inner)
        if nullable:
            document["type"] = ["object", "null"]
        return document
    raise AssertionError(kind)


def _object_schema(spec: dict[str, Any]) -> dict[str, Any]:
    properties = {key: _schema_for(type_spec) for key, type_spec in spec["required"].items()}
    properties.update({key: _schema_for(type_spec) for key, type_spec in spec["optional"].items()})
    document: dict[str, Any] = {"type": "object", "additionalProperties": False}
    if spec["required"]:
        document["required"] = list(spec["required"])
    document["properties"] = properties
    return document


def schema_document(file_name: str) -> dict[str, Any]:
    title, spec = SCHEMA_DOCUMENTS[file_name]
    document = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID_BASE + file_name,
        "title": title,
    }
    document.update(_object_schema(spec))
    return document


# --- bounded IO and path safety ----------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_bounded_json(path: Path) -> tuple[Any, str]:
    try:
        size = path.stat().st_size
    except OSError as exception:
        raise ValidationInputError("input_unreadable", f"{path.name}: {exception.strerror or exception}") from exception
    if size > MAX_INPUT_BYTES:
        raise ValidationInputError("input_too_large", f"{path.name}: {size} bytes exceeds {MAX_INPUT_BYTES}")
    try:
        data = path.read_bytes()
        parsed = read_json(path)
    except (OSError, ValueError) as exception:
        raise ValidationInputError("input_undecodable", f"{path.name}: {exception}") from exception
    return parsed, sha256_bytes(data)


def resolve_evidence_roots(plan: dict[str, Any], manifest_dir: Path) -> list[Path]:
    roots: list[Path] = []
    for raw in plan.get("evidenceRoots") or ["."]:
        try:
            roots.append((manifest_dir / raw).resolve())
        except (OSError, RuntimeError):
            continue
    return roots


def resolve_evidence_path(raw: str, manifest_dir: Path, roots: list[Path]) -> tuple[Path | None, str | None]:
    candidate_path = Path(raw)
    if not candidate_path.is_absolute():
        candidate_path = manifest_dir / candidate_path
    try:
        resolved = candidate_path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "evidence_missing"
    if not resolved.is_file():
        return None, "evidence_missing"
    for root in roots:
        if resolved == root or root in resolved.parents:
            return resolved, None
    return None, "evidence_outside_roots"


def verify_ref(ref: dict[str, Any], manifest_dir: Path, roots: list[Path]) -> tuple[Path | None, str | None]:
    resolved, problem = resolve_evidence_path(str(ref.get("path") or ""), manifest_dir, roots)
    if problem:
        return None, problem
    assert resolved is not None
    if resolved.stat().st_size == 0:
        return None, "evidence_missing"
    if sha256_file(resolved).lower() != str(ref.get("sha256") or "").lower():
        return None, "evidence_changed"
    return resolved, None


# --- adapter A: saved helper responses ---------------------------------------------------------

def _int_or_none(value: Any) -> int | None:
    return value if _is_int(value) else None


def normalize_helper_response(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise ValidationInputError("evidence_undecodable", "helper response is not a JSON object")
    payload_type = str(response.get("payload_type") or "")
    raw_payload = response.get("payload_json")
    decoded: dict[str, Any] | None = None
    if isinstance(raw_payload, str) and raw_payload.strip():
        try:
            candidate = json.loads(raw_payload)
        except ValueError as exception:
            raise ValidationInputError("evidence_undecodable", f"payload_json is not JSON: {exception}") from exception
        decoded = candidate if isinstance(candidate, dict) else None
    elif isinstance(raw_payload, dict):
        decoded = raw_payload
    error = response.get("error") if isinstance(response.get("error"), dict) else {}
    lifecycle = response.get("_xuunity_lifecycle") if isinstance(response.get("_xuunity_lifecycle"), dict) else {}
    transport = lifecycle.get("transport") if isinstance(lifecycle.get("transport"), dict) else {}
    normalized: dict[str, Any] = {
        "payloadType": payload_type,
        "stage": HELPER_STAGE_BY_PAYLOAD_TYPE.get(payload_type),
        "requestId": response.get("request_id") if isinstance(response.get("request_id"), str) else None,
        "startedAt": None,
        "completedAt": response.get("completed_at_utc") if isinstance(response.get("completed_at_utc"), str) else None,
        "producer": {"name": "xuunity-light-mcp-helper", "version": None, "route": None},
        "operationOutcome": "blocked",
        "executionBlocker": None,
        "diagnostics": None,
        "rebuild": None,
        "tests": None,
        "fieldPaths": [],
    }
    if decoded is None:
        code = str(error.get("code") or "payload_missing")
        normalized["executionBlocker"] = {"code": code, "message": str(error.get("message") or "")[:COMPACT_DETAIL_CHARS] or None}
        normalized["fieldPaths"] = ["error"]
        return normalized
    route_parts = [
        str(decoded.get("completion_basis") or ""),
        str(decoded.get("authoritative_state_source") or ""),
        str(transport.get("transport") or ""),
    ]
    normalized["producer"]["route"] = "|".join(route_parts)
    normalized["startedAt"] = decoded.get("started_at_utc") if isinstance(decoded.get("started_at_utc"), str) else None
    post_settle = _int_or_none(decoded.get("post_settle_error_count"))
    if payload_type == "unity.compile.player_scripts":
        result = decoded.get("result") if isinstance(decoded.get("result"), dict) else {}
        status = str(result.get("status") or "")
        if status == "passed":
            normalized["operationOutcome"] = "passed"
        elif status == "failed":
            normalized["operationOutcome"] = "failed"
        else:
            normalized["operationOutcome"] = "blocked"
            normalized["executionBlocker"] = {"code": status or "compile_status_missing", "message": None}
        warning_count = _int_or_none(result.get("warning_count"))
        unique = _int_or_none(result.get("unique_warning_count"))
        samples = result.get("warnings") if isinstance(result.get("warnings"), list) else []
        normalized["diagnostics"] = {
            "scope": "all",
            "complete": warning_count is not None,
            "warningCount": warning_count,
            "uniqueWarningCount": unique,
            "truncated": result.get("warnings_truncated") if isinstance(result.get("warnings_truncated"), bool) else None,
            "samples": [json.dumps(item, ensure_ascii=True, sort_keys=True)[:COMPACT_DETAIL_CHARS] for item in samples[:20]],
        }
        normalized["rebuild"] = {
            "status": result.get("rebuild_evidence_status") if isinstance(result.get("rebuild_evidence_status"), str) else None,
            "rebuiltAssemblyCount": _int_or_none(result.get("rebuilt_assembly_count")),
            "cachedAssemblyCount": _int_or_none(result.get("cached_assembly_count")),
        }
        normalized["fieldPaths"] = ["payload_json.result", "payload_json.completion_basis", "payload_json.post_settle_error_count"]
        if post_settle is not None:
            normalized["tests"] = {"verdict": None, "postSettleErrorCount": post_settle}
        return normalized
    if payload_type in ("unity.tests.run_editmode", "unity.tests.run_playmode"):
        verdict = decoded.get("test_verdict") if isinstance(decoded.get("test_verdict"), str) else None
        normalized["tests"] = {
            "verdict": verdict,
            "total": _int_or_none(decoded.get("total")),
            "passed": _int_or_none(decoded.get("passed")),
            "failed": _int_or_none(decoded.get("failed")),
            "skipped": _int_or_none(decoded.get("skipped")),
            "postSettleErrorCount": post_settle,
        }
        if verdict == "passed":
            normalized["operationOutcome"] = "passed"
        elif verdict == "runtime_timeout":
            normalized["operationOutcome"] = "blocked"
            normalized["executionBlocker"] = {"code": "runtime_timeout", "message": None}
        elif verdict in ("failed", "no_tests", "test_filter_no_match"):
            normalized["operationOutcome"] = "failed"
        else:
            normalized["operationOutcome"] = "blocked"
            normalized["executionBlocker"] = {"code": verdict or "test_verdict_missing", "message": None}
        normalized["fieldPaths"] = ["payload_json.test_verdict", "payload_json.total", "payload_json.passed", "payload_json.failed"]
        return normalized
    status = str(decoded.get("status") or "")
    if status in ("passed", "ok"):
        normalized["operationOutcome"] = "passed"
    elif status in ("failed", "error"):
        normalized["operationOutcome"] = "failed"
    else:
        normalized["operationOutcome"] = "blocked"
        normalized["executionBlocker"] = {"code": status or "status_missing", "message": None}
    normalized["fieldPaths"] = ["payload_json.status"]
    return normalized


# --- adapter B: reference consumer release verdict --------------------------------------------

_CONSUMER_STATUS_TO_OUTCOME = {
    "PASS": "passed",
    "REUSED": "passed",
    "FAIL": "failed",
    "BLOCKED": "blocked",
    "NOT_RUN": "not_run",
}
_CONSUMER_UNITY_CHECKS = {"unity_matrix", "compatibility", "sample_e2e", "lifecycle_tests", "android"}
_CONSUMER_STATIC_STAGE = {"toolchain_preflight": "resolve", "native_client_receipt": "client-integration"}
_CONSUMER_STATIC_CHANNEL = {"asset_store_validator": "direct-unity", "native_client_receipt": "native-mcp"}


def _consumer_outcome(status: Any) -> str:
    return _CONSUMER_STATUS_TO_OUTCOME.get(str(status or "").upper(), "blocked")


def _consumer_diagnostics(container: dict[str, Any]) -> dict[str, Any] | None:
    cleanliness = container.get("compiler_cleanliness")
    if not isinstance(cleanliness, dict):
        return None
    count = _int_or_none(cleanliness.get("count"))
    return {"scope": "all", "complete": count is not None, "warningCount": count, "uniqueWarningCount": None, "truncated": None, "samples": []}


def _consumer_stage_for_row(row: dict[str, Any]) -> str:
    required = [str(stage) for stage in row.get("required_stages") or []]
    if "player_run" in required:
        return "player-runtime"
    if "player_build" in required:
        return "export" if str(row.get("target") or "") == "iOS" else "build"
    if "tests" in required:
        return "editmode"
    return "compile"


def derive_from_consumer_verdict(
    verdict: Any,
    *,
    project_id: str,
    plan_id: str,
    verdict_ref: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(verdict, dict) or verdict.get("schema_version") != CONSUMER_VERDICT_SCHEMA_VERSION:
        raise ValidationInputError(
            "unknown_schema_version",
            f"consumer verdict schema_version {(verdict.get('schema_version') if isinstance(verdict, dict) else None)!r} is not supported",
        )
    checks = verdict.get("checks") if isinstance(verdict.get("checks"), dict) else {}
    impact = verdict.get("impact") if isinstance(verdict.get("impact"), dict) else {}
    digests = impact.get("digests") if isinstance(impact.get("digests"), dict) else {}
    artifact_check = checks.get("artifact") if isinstance(checks.get("artifact"), dict) else {}
    artifact = artifact_check.get("artifact") if isinstance(artifact_check.get("artifact"), dict) else {}
    identity = artifact.get("source_identity") if isinstance(artifact.get("source_identity"), dict) else {}
    digest = str(digests.get("executable_content_sha256") or "")
    if not digest:
        raise ValidationInputError("schema_violation", "consumer verdict has no impact.digests.executable_content_sha256")
    source_identity = {
        "algorithm": "sha256",
        "digest": digest,
        "manifestRef": None,
        "dirtyPaths": [str(item) for item in identity.get("dirty_paths") or []] if isinstance(identity.get("dirty_paths"), list) else None,
        "commit": str(identity.get("revision")) if identity.get("revision") else None,
    }
    required_checks = {str(name) for name in verdict.get("required_checks") or []}
    completed_at = verdict.get("completed_at_utc") if isinstance(verdict.get("completed_at_utc"), str) else None
    requirements: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []

    def add(requirement: dict[str, Any], receipt: dict[str, Any] | None) -> None:
        requirements.append(requirement)
        if receipt is not None:
            receipts.append(receipt)

    def base_receipt(requirement: dict[str, Any], status: Any, *, reason: Any = None, route: str) -> dict[str, Any]:
        outcome = _consumer_outcome(status)
        receipt: dict[str, Any] = {
            "receiptId": "verdict:" + requirement["id"],
            "requirementId": requirement["id"],
            "sourceIdentity": source_identity,
            "dimensions": requirement["dimensions"],
            "stage": requirement["stage"],
            "executionChannel": requirement["executionChannel"],
            "evidenceRef": verdict_ref,
            "evidenceKind": "raw",
            "producer": {"name": "consumer-release-runner", "version": CONSUMER_VERDICT_SCHEMA_VERSION, "route": route},
            "startedAt": None,
            "completedAt": completed_at,
            "operationOutcome": outcome,
            "reused": str(status or "").upper() == "REUSED",
            "originalRunAt": None,
        }
        if outcome in ("blocked", "not_run") and reason:
            receipt["executionBlocker"] = {"code": "consumer_blocked", "message": str(reason)[:COMPACT_DETAIL_CHARS]}
        return receipt

    def dims(unity_version: Any, target: Any, backend: Any, input_mode: Any) -> dict[str, Any]:
        return {
            "unityVersion": str(unity_version) if unity_version else None,
            "target": str(target) if target else None,
            "scriptingBackend": str(backend) if backend else None,
            "inputMode": str(input_mode) if input_mode else None,
        }

    matrix = checks.get("unity_matrix") if isinstance(checks.get("unity_matrix"), dict) else {}
    lanes = [lane for lane in matrix.get("lanes") or [] if isinstance(lane, dict)]
    compatibility = checks.get("compatibility") if isinstance(checks.get("compatibility"), dict) else {}
    for row in compatibility.get("rows") or []:
        if not isinstance(row, dict):
            continue
        matching = [lane for lane in lanes if lane.get("line") == row.get("line") and lane.get("target") == row.get("target")]
        lane = matching[0] if len(matching) == 1 else None
        channel = str((lane or {}).get("execution_channel") or "direct-unity")
        requirement = {
            "id": f"matrix:{row.get('line')}:{row.get('target')}",
            "required": True,
            "stage": _consumer_stage_for_row(row),
            "executionChannel": channel if channel in CHANNELS else "direct-unity",
            "dimensions": dims(row.get("unity_version") or (lane or {}).get("unity_version"), row.get("target"), row.get("backend"), None),
            "scene": None,
            "artifactRequired": False,
            "policy": {"warningBudget": 0, "diagnosticsScope": "all"},
        }
        receipt = None
        if lane is not None:
            receipt = base_receipt(requirement, lane.get("status"), reason=lane.get("reason"), route="checks.unity_matrix.lanes")
            receipt["diagnostics"] = _consumer_diagnostics(lane)
        elif len(matching) > 1:
            receipt = base_receipt(requirement, "BLOCKED", reason="duplicate_evidence_identity", route="checks.unity_matrix.lanes")
        add(requirement, receipt)

    sample = checks.get("sample_e2e") if isinstance(checks.get("sample_e2e"), dict) else {}
    for lane in sample.get("lanes") or []:
        if not isinstance(lane, dict):
            continue
        result = lane.get("result") if isinstance(lane.get("result"), dict) else {}
        channel = str(lane.get("execution_channel") or "direct-unity")
        requirement = {
            "id": f"sample:{lane.get('line')}:{lane.get('input_mode')}",
            "required": True,
            "stage": "playmode",
            "executionChannel": channel if channel in CHANNELS else "direct-unity",
            "dimensions": dims(lane.get("unity_version"), lane.get("target"), lane.get("backend"), lane.get("input_mode")),
            "scene": str(result.get("scene")) if result.get("scene") else None,
            "artifactRequired": False,
            "policy": {"warningBudget": 0, "diagnosticsScope": "all", "minTests": 1},
        }
        receipt = base_receipt(requirement, lane.get("status"), reason=lane.get("reason"), route="checks.sample_e2e.lanes")
        receipt["scene"] = requirement["scene"]
        receipt["diagnostics"] = _consumer_diagnostics(lane)
        editor = lane.get("editor_playmode") if isinstance(lane.get("editor_playmode"), dict) else {}
        total = _int_or_none(editor.get("total"))
        passed = _int_or_none(editor.get("passed"))
        receipt["tests"] = {
            "verdict": "passed" if receipt["operationOutcome"] == "passed" else None,
            "total": total,
            "passed": passed,
            "failed": (total - passed) if total is not None and passed is not None else None,
            "skipped": None,
        }
        add(requirement, receipt)

    lifecycle = checks.get("lifecycle_tests") if isinstance(checks.get("lifecycle_tests"), dict) else {}
    seen_versions: set[str] = set()
    for row in lifecycle.get("rows") or []:
        if not isinstance(row, dict):
            continue
        version = str(row.get("unity_version") or "")
        seen_versions.add(version)
        channel = str(row.get("execution_channel") or "helper-cli")
        requirement = {
            "id": f"lifecycle:{version}",
            "required": True,
            "stage": "editmode",
            "executionChannel": channel if channel in CHANNELS else "helper-cli",
            "dimensions": dims(version, row.get("target"), None, None),
            "scene": None,
            "artifactRequired": False,
        }
        receipt = base_receipt(requirement, row.get("status"), reason=lifecycle.get("reason"), route="checks.lifecycle_tests.rows")
        receipt["tests"] = {"verdict": "passed" if receipt["operationOutcome"] == "passed" else None}
        add(requirement, receipt)
    for version in lifecycle.get("required_editors") or []:
        if str(version) in seen_versions:
            continue
        add(
            {
                "id": f"lifecycle:{version}",
                "required": True,
                "stage": "editmode",
                "executionChannel": "helper-cli",
                "dimensions": dims(version, None, None, None),
                "scene": None,
                "artifactRequired": False,
            },
            None,
        )

    android = checks.get("android") if isinstance(checks.get("android"), dict) else {}
    profiles = android.get("profiles") if isinstance(android.get("profiles"), dict) else {}
    for profile, result in profiles.items():
        result = result if isinstance(result, dict) else {}
        requirement = {
            "id": f"android:{profile}",
            "required": "android" in required_checks,
            "stage": "device-runtime",
            "executionChannel": "any",
            "dimensions": dims(None, "Android", None, None),
            "scene": None,
            "artifactRequired": False,
        }
        status = result.get("status")
        if str(status or "").upper() == "NOT_RUN" and str(android.get("status") or "").upper() == "BLOCKED":
            status = "BLOCKED"
        add(requirement, base_receipt(requirement, status, reason=result.get("reason") or android.get("reason"), route="checks.android.profiles"))

    for name in sorted(set(checks) | required_checks):
        if name in _CONSUMER_UNITY_CHECKS or name == "reused_evidence":
            continue
        check = checks.get(name) if isinstance(checks.get(name), dict) else None
        channel = _CONSUMER_STATIC_CHANNEL.get(name, "any")
        requirement = {
            "id": f"check:{name}",
            "required": name in required_checks,
            "stage": _CONSUMER_STATIC_STAGE.get(name, "static"),
            "executionChannel": channel,
            "dimensions": dims(None, None, None, None),
            "scene": None,
            "artifactRequired": False,
        }
        if check is None:
            add(requirement, None)
            continue
        receipt = base_receipt(requirement, check.get("status"), reason=check.get("reason"), route=f"checks.{name}")
        if name == "native_client_receipt":
            receipt["clientKind"] = str(check.get("client_kind")) if check.get("client_kind") else None
            ref = check.get("receipt") if isinstance(check.get("receipt"), dict) else None
            if ref and isinstance(ref.get("path"), str) and isinstance(ref.get("sha256"), str):
                receipt["clientReceiptRef"] = {"path": ref["path"], "sha256": ref["sha256"]}
        add(requirement, receipt)

    plan = {
        "schemaVersion": PLAN_SCHEMA_VERSION,
        "planId": plan_id,
        "projectId": project_id,
        "runId": str(verdict.get("version")) if verdict.get("version") else None,
        "sourceIdentity": source_identity,
        "evidenceRoots": ["."],
        "requirements": requirements,
        "description": "Derived from a consumer release verdict; stages and channels follow the verdict's own rows.",
    }
    return plan, {"schemaVersion": RECEIPTS_SCHEMA_VERSION, "receipts": receipts}


# --- evaluation ------------------------------------------------------------------------------

def _select_receipt(requirement: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str | None]:
    if not candidates:
        return None, "receipt_missing"
    if len(candidates) == 1:
        return candidates[0], None
    pinned = requirement.get("receiptId")
    if pinned:
        for receipt in candidates:
            if receipt["receiptId"] == pinned:
                return receipt, None
        return None, "receipt_conflict"
    superseded = {rid for receipt in candidates for rid in receipt.get("supersedes") or []}
    remaining = [receipt for receipt in candidates if receipt["receiptId"] not in superseded]
    if len(remaining) == 1:
        return remaining[0], None
    return None, "receipt_conflict"


def _policy(requirement: dict[str, Any]) -> dict[str, Any]:
    policy = dict(requirement.get("policy") or {})
    policy.setdefault("warningBudget", None)
    policy.setdefault("diagnosticsScope", "all")
    policy.setdefault("requireMeasuredRebuild", False)
    policy.setdefault("minTests", None)
    policy.setdefault("semanticAssertions", [])
    return policy


def _client_receipt_verified(receipt: dict[str, Any], manifest_dir: Path, roots: list[Path], details: list[str]) -> bool:
    ref = receipt.get("clientReceiptRef")
    if not isinstance(ref, dict):
        details.append("native row has no clientReceiptRef")
        return False
    resolved, problem = verify_ref(ref, manifest_dir, roots)
    if problem or resolved is None:
        details.append(f"clientReceiptRef {problem}")
        return False
    try:
        document = read_json(resolved)
    except (OSError, ValueError):
        details.append("clientReceiptRef is not JSON")
        return False
    tool_result = document.get("tool_result") if isinstance(document, dict) and isinstance(document.get("tool_result"), dict) else document
    server_info = tool_result.get("mcp_server_info") if isinstance(tool_result, dict) else None
    if not isinstance(server_info, dict) or not str(server_info.get("version") or "").strip():
        details.append("client receipt lacks mcp_server_info.version")
        return False
    client_kind = str(tool_result.get("client_kind") or receipt.get("clientKind") or "").strip().lower()
    if client_kind and client_kind != "mcp_server":
        details.append(f"client receipt reports client_kind={client_kind}")
        return False
    return True


def evaluate_requirement(
    requirement: dict[str, Any],
    receipts: list[dict[str, Any]],
    *,
    plan: dict[str, Any],
    manifest_dir: Path,
    roots: list[Path],
) -> dict[str, Any]:
    policy = _policy(requirement)
    row: dict[str, Any] = {
        "requirementId": requirement["id"],
        "required": requirement["required"],
        "stage": requirement["stage"],
        "executionChannel": requirement["executionChannel"],
        "dimensions": requirement["dimensions"],
        "scene": requirement.get("scene"),
        "matchedReceiptIds": [],
        "operationOutcome": None,
        "outcome": "not_run",
        "reused": False,
        "originalRunAt": None,
        "reasons": [],
        "details": [],
        "policy": policy,
        "provenance": {},
    }
    reasons: list[str] = row["reasons"]
    details: list[str] = row["details"]

    def finish(outcome: str, *codes: str) -> dict[str, Any]:
        for code in codes:
            if code not in reasons:
                reasons.append(code)
        row["outcome"] = outcome
        return row

    candidates = [receipt for receipt in receipts if receipt["requirementId"] == requirement["id"]]
    row["matchedReceiptIds"] = [receipt["receiptId"] for receipt in candidates]
    receipt, problem = _select_receipt(requirement, candidates)
    if receipt is None:
        if problem == "receipt_missing":
            return finish("not_run", "receipt_missing")
        details.append(f"{len(candidates)} receipts match without a pin or supersedes chain")
        return finish("blocked", problem or "receipt_conflict")
    row["matchedReceiptIds"] = [receipt["receiptId"]]
    row["reused"] = bool(receipt.get("reused"))
    row["originalRunAt"] = receipt.get("originalRunAt")
    row["provenance"] = {
        "evidenceRef": receipt["evidenceRef"],
        "evidenceKind": receipt.get("evidenceKind", "raw"),
        "producer": receipt.get("producer"),
        "requestId": receipt.get("requestId"),
        "fieldPaths": [],
    }

    plan_identity = plan["sourceIdentity"]
    receipt_identity = receipt["sourceIdentity"]
    if (receipt_identity["algorithm"], receipt_identity["digest"].lower()) != (plan_identity["algorithm"], plan_identity["digest"].lower()):
        details.append("receipt source digest differs from the plan")
        return finish("blocked", "source_identity_mismatch")
    if receipt["dimensions"] != requirement["dimensions"]:
        details.append("receipt dimensions differ from the requirement")
        return finish("blocked", "dimension_mismatch")
    if requirement.get("scene") is not None and receipt.get("scene") != requirement.get("scene"):
        details.append("receipt scene differs from the requirement")
        return finish("blocked", "scene_mismatch")
    if receipt["stage"] != requirement["stage"]:
        details.append(f"receipt stage {receipt['stage']} cannot satisfy {requirement['stage']}")
        return finish("blocked", "stage_mismatch")
    if requirement["executionChannel"] == "native-mcp":
        if receipt["executionChannel"] != "native-mcp" or not _client_receipt_verified(receipt, manifest_dir, roots, details):
            return finish("blocked", "channel_unverified")
    elif requirement["executionChannel"] != "any" and receipt["executionChannel"] != requirement["executionChannel"]:
        details.append(f"receipt channel {receipt['executionChannel']} differs from {requirement['executionChannel']}")
        return finish("blocked", "channel_unverified")
    if requirement.get("executionLane") and receipt.get("executionLane") != requirement.get("executionLane"):
        details.append("receipt execution lane differs from the requirement")
        return finish("blocked", "dimension_mismatch")

    evidence_path, evidence_problem = verify_ref(receipt["evidenceRef"], manifest_dir, roots)
    if evidence_problem or evidence_path is None:
        details.append(f"evidenceRef {receipt['evidenceRef'].get('path')}: {evidence_problem}")
        return finish("blocked", evidence_problem or "evidence_missing")

    operation_outcome = receipt.get("operationOutcome")
    diagnostics = receipt.get("diagnostics")
    rebuild = receipt.get("rebuild")
    tests = receipt.get("tests")
    blocker = receipt.get("executionBlocker")
    if receipt.get("evidenceKind", "raw") == "helper_response":
        try:
            normalized = normalize_helper_response(read_json(evidence_path))
        except (OSError, ValueError) as exception:
            details.append(f"helper response undecodable: {exception}")
            return finish("blocked", "evidence_undecodable")
        if normalized["stage"] is not None and normalized["stage"] != requirement["stage"]:
            details.append(f"helper payload {normalized['payloadType']} cannot satisfy {requirement['stage']}")
            return finish("blocked", "stage_mismatch")
        operation_outcome = normalized["operationOutcome"]
        diagnostics = normalized["diagnostics"] if diagnostics is None else diagnostics
        rebuild = normalized["rebuild"] if rebuild is None else rebuild
        tests = normalized["tests"] if tests is None else tests
        blocker = normalized["executionBlocker"] if blocker is None else blocker
        row["provenance"]["producer"] = normalized["producer"]
        row["provenance"]["requestId"] = normalized["requestId"]
        row["provenance"]["fieldPaths"] = normalized["fieldPaths"]
    row["operationOutcome"] = operation_outcome

    if operation_outcome == "not_run":
        return finish("not_run", "receipt_missing")
    if operation_outcome == "blocked":
        code = str((blocker or {}).get("code") or "")
        if (blocker or {}).get("message"):
            details.append(str(blocker["message"]))
        if code == "runtime_timeout":
            return finish("blocked", "runtime_timeout")
        if code:
            details.append(f"blocker code {code}")
        return finish("blocked", "capability_unavailable")
    if operation_outcome == "failed":
        if requirement["stage"] in TEST_STAGES and tests and tests.get("verdict") not in (None, "passed"):
            details.append(f"test verdict {tests.get('verdict')}")
            return finish("fail", "operation_failed", "test_verdict_not_passed")
        return finish("fail", "operation_failed")

    failures: list[str] = []
    blocks: list[str] = []
    if requirement["stage"] in TEST_STAGES:
        if not tests or tests.get("verdict") != "passed":
            details.append(f"test verdict {(tests or {}).get('verdict')!r} is not passed")
            failures.append("test_verdict_not_passed")
        else:
            total = tests.get("total")
            failed = tests.get("failed")
            minimum = policy.get("minTests")
            if minimum is not None and (total is None or total < minimum):
                details.append(f"selected tests {total} below minimum {minimum}")
                failures.append("test_count_insufficient")
            if failed not in (None, 0):
                details.append(f"{failed} failed tests")
                failures.append("test_verdict_not_passed")
    post_settle = (tests or {}).get("postSettleErrorCount") if tests else None
    if post_settle not in (None, 0):
        details.append(f"{post_settle} post-settle errors")
        failures.append("post_settle_errors")
    for name in policy["semanticAssertions"]:
        matches = [item for item in receipt.get("semanticAssertions") or [] if item.get("name") == name]
        if not matches or not all(item.get("passed") for item in matches):
            details.append(f"semantic assertion {name} not proven")
            failures.append("semantic_assertion_failed")
    budget = policy.get("warningBudget")
    if budget is not None:
        count = (diagnostics or {}).get("warningCount") if diagnostics else None
        complete = bool((diagnostics or {}).get("complete")) if diagnostics else False
        scope = (diagnostics or {}).get("scope") if diagnostics else None
        if count is None or not complete:
            details.append("warning counts missing or incomplete")
            blocks.append("diagnostics_unmeasured")
        elif policy["diagnosticsScope"] == "package" and scope != "package" and count > 0:
            details.append("package-only cleanliness needs package-scoped ownership when global warnings exist")
            blocks.append("diagnostics_unmeasured")
        elif count > budget:
            details.append(f"{count} warnings exceed budget {budget}")
            failures.append("warning_budget_exceeded")
    if policy.get("requireMeasuredRebuild"):
        status = (rebuild or {}).get("status") if rebuild else None
        rebuilt = (rebuild or {}).get("rebuiltAssemblyCount") if rebuild else None
        if status != "measured":
            details.append(f"rebuild evidence {status!r} is not measured")
            blocks.append("rebuild_unmeasured")
        elif not rebuilt:
            details.append("measured rebuild compiled zero assemblies")
            blocks.append("rebuild_cached_only")
    if requirement["artifactRequired"]:
        artifact = receipt.get("artifact")
        if not isinstance(artifact, dict):
            details.append("no artifact identity on the receipt")
            blocks.append("artifact_missing")
        else:
            _, artifact_problem = verify_ref(artifact, manifest_dir, roots)
            if artifact_problem == "evidence_changed":
                details.append("artifact content differs from the recorded identity")
                blocks.append("artifact_changed")
            elif artifact_problem:
                details.append(f"artifact {artifact.get('path')}: {artifact_problem}")
                blocks.append("artifact_missing")
    if failures:
        return finish("fail", *failures, *blocks)
    if blocks:
        return finish("blocked", *blocks)
    return finish("pass")


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(rows), "pass": 0, "fail": 0, "blocked": 0, "not_run": 0}
    for row in rows:
        counts[row["outcome"]] += 1
    return counts


def aggregate_verdict(required_counts: dict[str, int]) -> str:
    if required_counts["fail"]:
        return "fail"
    if required_counts["blocked"]:
        return "blocked"
    if required_counts["not_run"]:
        return "partial"
    return "pass"


def evaluate(
    plan: dict[str, Any],
    receipts_document: dict[str, Any],
    *,
    manifest_dir: Path,
    plan_sha256: str,
    report_ref: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    roots = resolve_evidence_roots(plan, manifest_dir)
    receipts = receipts_document["receipts"]
    rows = [
        evaluate_requirement(requirement, receipts, plan=plan, manifest_dir=manifest_dir, roots=roots)
        for requirement in plan["requirements"]
    ]
    required_rows = [row for row in rows if row["required"]]
    optional_rows = [row for row in rows if not row["required"]]
    required_counts = _counts(required_rows)
    gaps: list[str] = []
    for row in rows:
        if row["outcome"] != "pass":
            gaps.append(f"{row['requirementId']}: {row['outcome']} ({', '.join(row['reasons'])})")
    known_ids = {requirement["id"] for requirement in plan["requirements"]}
    orphans = sorted({receipt["requirementId"] for receipt in receipts if receipt["requirementId"] not in known_ids})
    if orphans:
        gaps.append("receipts reference unknown requirements: " + ", ".join(orphans))
    report: dict[str, Any] = {
        "schemaVersion": ACCEPTANCE_SCHEMA_VERSION,
        "evaluatorVersion": EVALUATOR_VERSION,
        "planId": plan["planId"],
        "planSha256": plan_sha256,
        "projectId": plan["projectId"],
        "runId": plan.get("runId"),
        "sourceIdentity": plan["sourceIdentity"],
        "verdict": aggregate_verdict(required_counts),
        "required": required_counts,
        "optional": _counts(optional_rows),
        "reusedCount": sum(1 for row in rows if row["outcome"] == "pass" and row["reused"]),
        "rows": rows,
        "validationGaps": gaps,
        "reportRef": {"path": report_ref},
        "generatedAt": generated_at,
    }
    return report


def exit_code_for(report: dict[str, Any]) -> int:
    return 0 if report["verdict"] == "pass" else 1


def _next_action(report: dict[str, Any]) -> str:
    verdict = report["verdict"]
    if verdict == "pass":
        return "accepted"
    if verdict == "fail":
        return "fix_failed_rows_then_reevaluate"
    if verdict == "blocked":
        return "resolve_blocked_rows_or_record_named_gaps"
    return "supply_missing_receipts"


def compact_envelope(report: dict[str, Any], *, exit_code: int, report_path: str) -> dict[str, Any]:
    problem_rows = [row for row in report["rows"] if row["required"] and row["outcome"] != "pass"]
    first_reasons = [
        {
            "requirementId": row["requirementId"],
            "outcome": row["outcome"],
            "reasons": row["reasons"][:3],
            "detail": (row["details"][0][:COMPACT_DETAIL_CHARS] if row["details"] else ""),
        }
        for row in problem_rows[:COMPACT_REASON_ROWS]
    ]
    return {
        "payload_mode": "compact_validation_acceptance",
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "action": "evaluate_validation_evidence",
        "exit_code": exit_code,
        "outcome": "ok" if exit_code == 0 else "error",
        "verdict": report["verdict"],
        "plan_id": report["planId"],
        "plan_sha256": report["planSha256"],
        "evaluator_version": report["evaluatorVersion"],
        "required": report["required"],
        "optional_total": report["optional"]["total"],
        "reused_count": report["reusedCount"],
        "first_reasons": first_reasons,
        "reasons_truncated": len(problem_rows) > COMPACT_REASON_ROWS,
        "artifacts": [report_path],
        "recommended_next_action": _next_action(report),
        "full_payload_available": True,
        "full_payload_cli_argument": "--output full",
    }


def invalid_envelope(exception: Exception, *, report_path: str | None) -> dict[str, Any]:
    code = getattr(exception, "code", "evaluation_invalid")
    return {
        "payload_mode": "compact_validation_acceptance",
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "action": "evaluate_validation_evidence",
        "exit_code": 2,
        "outcome": "error",
        "verdict": None,
        "reason": "evaluation_invalid",
        "error": {"code": str(code), "message": str(exception)[:COMPACT_DETAIL_CHARS * 2]},
        "artifacts": [report_path] if report_path else [],
        "recommended_next_action": "fix_input_then_reevaluate; do not record this as a blocked row",
        "full_payload_available": False,
    }
