# Validation Evidence and Release Acceptance

Date: `2026-09-21`
Status: `implemented (offline evaluator, schemas, adapters, docs); consumer adoption partially implemented; independent acceptance pending`
Owner: MCP Python host (`scripts/testing/`), workflow templates, agent docs.
Input: a host-private release-validation retrospective dated 2026-09-21. Its
consumer identity, paths, request ids and raw evidence are deliberately not
reproduced here.

## Problem

A successful Unity operation was repeatedly summarized as broader acceptance:
a compile as regression coverage, an APK build as platform validation, helper
readiness as native MCP-client wiring. Warning counts existed in every compile
payload but were applied as a release decision late. The join between a
release owner's requirement rows and MCP evidence receipts lived only inside
one consumer's release scripts, so nothing reusable checked it.

The reference consumer's own closeout runner already produced a correct
fixed-denominator `BLOCKED` verdict; the gap was between the tool and the
reader, and the lack of a reusable machine-checked join.

## Desired behavior

A consumer supplies an explicit validation plan and evidence receipts. A
deterministic offline evaluator reports acceptance per required row and keeps
the full denominator. It cannot turn missing evidence into PASS, substitute a
weaker stage, or relabel CLI evidence as native MCP-client verification.
Unity execution, journaling, recovery and transport are unchanged.

Example: an Android APK build passes while its required device-runtime row is
blocked by a missing device. The report says `1/2 pass, 1 blocked`; the APK
stays a valid artifact; publication acceptance stays blocked.

## Existing contracts reused

- Saved helper responses: `{request_id, status, completed_at_utc,
  payload_type, payload_json (string), error, _xuunity_lifecycle}`. Compile
  facts are in decoded `payload_json.result` (`status`, `warning_count`,
  `unique_warning_count`, `warnings_truncated`, `rebuilt_assembly_count`,
  `cached_assembly_count`, `rebuild_evidence_status`); test facts are top-level
  keys of decoded `payload_json` (`test_verdict`, `total`, `passed`, `failed`,
  `skipped`, `post_settle_error_count`). The outer `status=ok` never overrides
  the payload.
- Producer-side verdict owners: `templates/server_operation_evidence.py`
  (`test_verdict` in `passed`, `failed`, `no_tests`, `test_filter_no_match`,
  `runtime_timeout`), the editor compile utility (error-based compile status),
  `scripts/testing/run_multi_project.py::normalize_compile_evidence`
  (`execution_lane` in `batch`, `gui`, `none`).
- Journal `client_kind` (`mcp_server`, `cli`) and `client_session_id` are
  env-configurable and are traceability, not attestation.
  `unity_status_summary` writes no journal event and the protocol layer keeps
  no client identity, so a native-client receipt is operator-captured.
- Compact output: `templates/server_launcher.py` `COMPACT_OUTPUT_MAX_BYTES`
  and `_bounded_compact_json`; the evaluator reuses the encoder.
- Ledger conventions from `scripts/testing/run_consumer_rollout.py`:
  `schema_version`, fixed denominator, `payload_mode: compact_*`,
  `--output compact|full`, `full_payload_cli_argument`.
- `templates/workflows/evidence_summary.schema.json` v1 is a documented
  closeout contract referenced by the workflow templates; no code emits or
  validates it. It stays byte-identical.
- The host is Python 3.10+ with no third-party dependency. Schema strictness is
  enforced by hand-written validators; the JSON schema files are generated from
  the same specs and a test fails when they drift.

## Architecture

```text
Owner-approved plan ─────────────────────────┐
                                             v
Saved helper responses ─> adapter A ─> receipts ─> deterministic evaluator
Consumer release verdict > adapter B ─┘                   |
                                          full report + bounded compact envelope
                                                          |
                                                 consumer release gate
```

Evaluation is read-only except for the requested report. Receipt paths are
local files resolved against the receipts directory, must stay inside declared
evidence roots after `resolve(strict=True)`, and are hash-verified. Missing or
unreadable files are evidence gaps, never empty success.

## Interfaces

```bash
python3 scripts/testing/evaluate_validation_evidence.py \
  --plan PLAN --receipts RECEIPTS --report REPORT [--output compact|full]
python3 scripts/testing/evaluate_validation_evidence.py \
  --consumer-verdict VERDICT --report REPORT [--project-id ID --plan-id ID]
```

Exit codes: `0` accepted; `1` valid evaluation with failed, blocked or partial
required rows; `2` invalid input, schema or IO, with a bounded envelope
`reason: evaluation_invalid`. A caller that maps exit `2` to a blocked row must
instead treat it as `evaluation_invalid` with no acceptance rows.

Schemas under `templates/workflows/`, all strict:

- `validation_plan.schema.json` (`xuunity.light-mcp.validation-plan.v1`):
  `planId`, `projectId`, `sourceIdentity {algorithm, digest, manifestRef,
  dirtyPaths, commit}`, `evidenceRoots`, `requirements[]` with `id`,
  `required`, `stage`, `executionChannel`, optional `executionLane`,
  `dimensions {unityVersion, target, scriptingBackend, inputMode}`, `scene`,
  `policy {warningBudget, diagnosticsScope, requireMeasuredRebuild, minTests,
  semanticAssertions}`, `artifactRequired`, optional `receiptId` pin.
- `validation_receipts.schema.json` (`xuunity.light-mcp.validation-receipts.v1`):
  `receipts[]` with identity and binding fields, `evidenceRef {path, sha256}`,
  `evidenceKind` (`raw` or `helper_response`), `producer`, timestamps,
  `operationOutcome`, optional `clientReceiptRef`, `artifact`, `diagnostics`,
  `rebuild`, `tests`, `semanticAssertions`, `executionBlocker`, `reused`,
  `originalRunAt`, `supersedes`.
- `validation_acceptance.schema.json`
  (`xuunity.light-mcp.validation-acceptance.v1`): verdict, required and
  optional counts, `reusedCount`, ordered rows with reason codes and
  provenance, validation gaps, report reference.

Stages: `static`, `resolve`, `compile`, `editmode`, `playmode`, `build`,
`export`, `player-runtime`, `device-runtime`, `client-integration`. They are
exact capabilities, not a ladder. Channels: `native-mcp`, `helper-cli`,
`direct-unity`, `any`; `any` never satisfies a native row.

## Evaluation rules

1. Validate schemas, unique ids, evidence roots and size limits (10 MiB per
   input, 10,000 rows or receipts).
2. Match requirement id, source digest, exact dimensions, scene, stage,
   channel and lane. Any mismatch blocks the row with a named reason.
3. With more than one candidate receipt, the plan's `receiptId` pin or a
   receipt's `supersedes` list decides; otherwise `receipt_conflict`.
4. Helper responses are decoded by the evaluator; a compile payload offered for
   a test row is `stage_mismatch`.
5. Tests pass only with `test_verdict == passed`, `failed == 0` and the plan
   minimum; `runtime_timeout` blocks; `no_tests`, `test_filter_no_match` and
   `failed` fail. Post-settle errors fail the row.
6. Diagnostics policy is separate from the operation outcome: missing or
   incomplete counts block (`diagnostics_unmeasured`), counts above budget fail
   (`warning_budget_exceeded`); package-only cleanliness with global warnings
   needs package-scoped ownership.
7. Measured rebuild is required only where the plan asks; unmeasured or
   cached-only evidence blocks.
8. A required artifact must exist, be non-empty and match its hash; a
   historical build stays `operationOutcome: passed` while deliverability is
   blocked.
9. Native rows need `clientReceiptRef` pointing at the `unity_status_summary`
   result captured inside the client session with `mcp_server_info.version`
   and no `client_kind=cli`; otherwise `channel_unverified`.
10. Aggregate required rows: any fail gives `fail`; else any blocked gives
    `blocked`; else any not_run gives `partial`; else `pass`. Optional rows
    never change the verdict. Reused receipts stay visible.
11. The compact envelope carries verdict, counts, reused count, the first
    actionable reasons and the report path, bounded by the launcher encoder.

## Validation order before an expensive matrix

Capability inventory, static fixture checks, compile with measured rebuild and
warning policy, one focused sample PlayMode scenario on the real input route,
repeated setup plus a sequential target transition, then the declared matrix,
then build, runtime and device rows, then receipt aggregation with deliverable
identity. The reference consumer already runs in this order; the MCP promotes
it in `docs/operations/SMOKE_TESTS.md`.

## Implementation status

| Package | Status |
| --- | --- |
| Schemas, generated from specs, with drift test | implemented |
| Evaluator and CLI (`scripts/testing/evaluate_validation_evidence.py`, `validation_acceptance.py`) | implemented |
| Adapter A (saved helper responses) and adapter B (consumer release verdict) | implemented |
| Compact projection through the launcher encoder | implemented |
| Docs: agent workflows, smoke tests, continuation, README cross-link | implemented |
| Consumer adoption: execution channel per row, native-client receipt check | implemented in the reference consumer's runner; not yet exercised in a fresh closeout run |
| Independent non-author acceptance | pending |

Validation evidence and counts are recorded in `DESIGN_PLAN_HISTORY.md`.

## Non-goals

CI scheduler, process manager, SDK installation, publisher automation,
permission expansion, click engine, transport rewrite, universal device
support, warning suppression, migration of existing workflow JSON, MCP tool
registration in the first delivery, third-party Python dependencies,
server-side client attestation.

## Open decision

D2: a host-only `client_probe` journal event when `unity_status_summary` is
served to a native client (`client_kind`, `client_session_id`,
`mcp_server_info.version`). Python host code, no bridge change, but a runtime
behavior change; it belongs in its own change after the offline evaluator has
been used on one real release.

## Rollback

Remove the evaluator invocation; keep every evidence and report artifact and
the v1 evidence summary. Strict acceptance becomes unavailable, never green.
