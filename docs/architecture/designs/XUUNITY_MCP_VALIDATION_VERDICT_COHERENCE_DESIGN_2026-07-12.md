# XUUnity MCP Validation Verdict Coherence Design

Date: `2026-07-12`
Status: `partially implemented; portfolio evidence slice host-validated`
Scope: public operator verdicts for post-change smoke and multi-project
validation selection

## Goal

Make a completed Unity operation and a passed compile matrix mean the same
thing on every operator-facing surface that consumes them. A caller must not
need to inspect a raw journal to learn that Unity completed, and a project must
not disappear between a successful compile lane and the following GUI test
lane because that compile used a different valid execution lane.

This design is public-safe: it describes reusable contracts only and excludes
consumer projects, local paths, request identifiers, and run-specific counts.

## Current Shape

Two independently useful mechanisms already exist:

- request journals can prove Unity completion after the original host response
  is missing; `request-final-status` projects that as a compact terminal
  disposition;
- batch compile status records distinguish `passed_via_batch` from
  `passed_via_gui_fallback`.

The remaining coherence gaps are at the boundaries:

1. The post-change shell runner still invokes `python3` directly in several
   places, so its own diagnostics and summaries can fail under a restricted
   caller `PATH` even when the MCP launcher found a supported Python runtime.
2. The portfolio status builder reads matrix counts only from
   `result_summary.matrix`. A GUI fallback can carry its real matrix under the
   bridge payload instead, leaving a truthful success verdict with misleading
   zero counters.
3. The GUI subset selector independently reimplements green-status logic and
   accepts only the batch-shaped matrix field. It can therefore reject a
   legitimate fallback success that the aggregate itself accepts.
4. Cached negative license evidence can decide the fallback lane without a
   compact freshness signal or a bounded recheck policy.

## Implementation Status (2026-07-12)

Implemented and host-regression-validated:

- persisted batch statuses now normalize batch and GUI fallback matrices into
  `compile_evidence`; GUI fallback counters come from the structured bridge
  payload rather than being reported as zero;
- aggregate verdicts and GUI subset selection consume the same evidence helper;
- explicit batch-result selection emits coverage accounting and fails before
  workers start when a status is malformed, an eligible root is missing or
  duplicated, or eligible and selected counts differ;
- legacy successful fallback statuses remain selectable and are labelled in the
  selection summary;
- compact batch rows and status files expose license cache provenance, probe
  timestamp, and calculated age when available;
- smoke documentation and CLI help describe the lane-agnostic selection and
  fail-closed contract.

Deferred design scope:

- bounded refresh of stale negative license evidence before GUI fallback;
- launcher runtime-info and removal of direct `python3` calls from the
  post-change smoke template;
- representative live Unity fallback-to-GUI-subset proof.

## Architecture Decision

Keep the existing request journal and lane abstractions. Add two narrow
normalization boundaries rather than teaching every runner to interpret raw
payload shapes or launcher environment details.

```text
Unity / batch result
  -> normalize_compile_evidence
  -> persisted per-project status
  -> aggregate summary + GUI-subset selector

launcher Python discovery
  -> runtime diagnostics / selected interpreter
  -> post-change shell runner
  -> smoke summaries and recovery commands
```

No new service, transport, Unity runtime package, or project-specific hook is
introduced.

## 1. Canonical Compile Evidence

### Ownership

`scripts/testing/run_multi_project.py` owns the normalized compile evidence
for its persisted `*_status.json` artifacts. Both the compact aggregate and
`--from-batch-results` selection must use the same pure helper; neither may
reimplement lane-specific green logic.

### Contract

Add a versioned `compile_evidence` object to each batch status:

```json
{
  "schema_version": 1,
  "outcome": "passed",
  "evidence_source": "gui_fallback_matrix",
  "execution_lane": "gui",
  "matrix": {
    "status": "passed",
    "total": 6,
    "passed": 6,
    "failed": 0,
    "skipped": 0
  }
}
```

Allowed values:

- `outcome`: `passed`, `failed`, or `unproven`;
- `evidence_source`: `batch_result_summary`, `gui_fallback_matrix`,
  `legacy_status`, or `none`;
- `execution_lane`: `batch`, `gui`, or `none`.

Top-level `matrix_status`, count fields, and `operator_verdict` remain as
compatibility projections for one release line. They are derived from
`compile_evidence`, never used as an alternate source of truth.

### Extraction and Compatibility

`normalize_compile_evidence(payload, result_summary)` must read only
structured result sources, in this order:

1. `result_summary.matrix` for normal batch execution;
2. the decoded `bridge_response.payload_json` matrix for GUI fallback;
3. a deliberately labelled `legacy_status` projection when loading historical
   status files that have no normalized object.

The helper must validate that counters are non-negative integers and that a
passed matrix has `failed == 0`. It must not infer a matrix from an artifact
path, log text, or a generic transport success.

For historical status files, the compatibility adapter may accept the existing
successful operator-verdict categories only when their recorded successful
Unity/lane facts agree. It must label the result `legacy_status` in the
selection summary. New runs must always produce a matrix-backed normalized
object.

### Selection Contract

Replace `collect_green_projects_from_batch_results()` with a function that
returns a `BatchSelectionPlan`, not just a list of paths. It contains:

- status files found and parsed;
- eligible statuses, selected distinct project roots, and exclusions grouped by
  normalized outcome;
- malformed, missing-root, duplicate-root, and legacy-status diagnostics;
- whether coverage is complete.

`--from-batch-results` is an explicit selection request. It must never fall
back to auto-discovering every project when the plan selects zero projects.
Instead it prints a compact `selection_input_invalid` or
`selection_coverage_mismatch` decision and exits before opening editors.

Before workers start, emit a bounded summary containing
`status_files`, `eligible_projects`, `selected_projects`,
`excluded_projects`, and `legacy_projects`. A mismatch between eligible and
selected distinct roots is a fail-closed error. Operators who intentionally
want a partial set must use explicit `--project-root` inputs rather than a
batch-results selector.

This makes the coverage invariant explicit:

```text
Every compile-evidence outcome=passed project from the requested batch result
set receives exactly one GUI subset worker, unless the command fails before
workers start with a named selection error.
```

## 2. License Evidence Freshness

Keep license probing centralized in `server_license.py`; do not duplicate
cache handling in the portfolio runner.

Every compact batch status and aggregate row must surface safe decision facts:

- `license_probe_source`: `fresh`, `cached`, `override`, or `unavailable`;
- `license_probe_observed_at_utc`;
- `license_probe_age_seconds` when calculable;
- `license_probe_freshness`: `fresh`, `cached_recent`, `cached_stale`, or
  `unknown`.

When a cached negative capability result would change `auto` from batch to GUI,
the batch-lane owner performs one bounded refresh before choosing fallback if
the entry is older than the documented negative-result freshness window. The
window is a named server policy constant and is covered by fake-clock tests;
it is not embedded in the portfolio runner. A failed refresh preserves the
original evidence and reports its freshness rather than silently claiming a
fresh decision.

Cached positive and unknown evidence retain the existing fast path unless the
caller explicitly requests refresh. This limits extra startup cost to the
case where stale negative evidence could suppress the stronger batch lane.

## 3. Terminal Delivery and Launcher Diagnostics

The existing journal-backed terminal dispositions remain the sole authority
for recovered request completion. In particular, a journal-confirmed `ok`
completion with missing host delivery remains:

```text
terminal_disposition=unity_completed_host_delivery_unproven
safe_next_action=continue_without_retry
```

Do not add a second recovery state machine in the smoke runner.

### Runtime Resolution Boundary

Add a small Python-owned launcher runtime-info operation that reports the
interpreter selected by the normal launcher discovery chain. The post-change
runner calls it once before its first Python-dependent phase, reads a strict
newline-safe key/value response without `eval`, and uses that interpreter for
all its embedded Python snippets.

The compact default prints only non-sensitive facts such as shell kind, Python
major/minor version, resolution source, and whether a usable interpreter was
selected. An explicit local diagnostic mode may include normalized shell-facing
paths. Normal MCP responses and docs must not expose workstation paths.

The root shell launcher stays thin. Python owns interpreter discovery and
runtime metadata; the smoke shell only consumes the resolved value and emits
phase lines. This also keeps Windows Git Bash path normalization in one tested
place.

## Rejected Alternatives

| Alternative | Rejection reason |
| --- | --- |
| Let the selector trust `matrix_status` plus a special GUI exception | Recreates divergent green logic and will miss the next legitimate lane. |
| Treat any successful GUI operation as matrix proof | A transport success alone cannot prove all matrix lanes or counts. |
| Keep auto-discovery when batch selection is empty | Turns an explicit scoped validation request into an unexpected full run. |
| Print full executable paths in every compact result | Leaks host-specific detail and is unnecessary for normal decisions. |
| Re-probe every cached license result | Adds portfolio latency even when cached evidence does not weaken the selected lane. |
| Add runner-side journal interpretation | Duplicates the existing terminal verdict owner and risks contradictory recovery advice. |

## Migration and Compatibility

1. Introduce the normalization and selection-plan helpers with unit tests while
   retaining the current top-level fields.
2. Update batch writer, compact aggregate, and GUI selector in the same change;
   no mixed old/new green predicates may remain.
3. Add compact selection output and fail-closed handling for explicit batch
   result inputs.
4. Add license freshness projections and stale-negative recheck behavior in
   the server lane owner.
5. Add launcher runtime-info, consume it from the post-change runner, and
   remove direct `python3` calls from that runner.
6. Update smoke documentation, CLI help, CHANGELOG, and this plan's status only
   after implementation evidence is recorded.

## Validation

### Host regression tests

- batch result with a normal matrix selects exactly one project;
- GUI fallback with a bridge-payload matrix preserves true counters and selects
  exactly one project;
- legacy successful fallback status is labelled and selected compatibly;
- malformed status, missing root, duplicate root, zero eligible, and
  eligible/selected mismatch fail before worker launch;
- a failed or unproven matrix is never selected;
- cached recent negative license evidence does not re-probe, while stale
  negative evidence re-probes once and exposes freshness facts;
- compact default terminal verdict remains unchanged for delivery-unproven
  completion, including lifecycle-generation evidence;
- a runner launched through an absolute Bash with a restricted `PATH` and a
  launcher-resolved Python still emits diagnostics and completes its
  Python-backed summary path;
- Windows path and interpreter override regressions continue to use the
  existing cross-platform launcher contracts.

### Live Unity evidence

Run one representative compile matrix forced through the GUI fallback and feed
its persisted result directory directly into the GUI subset runner. The
selection summary must show complete coverage, real matrix counters, and the
license freshness class. Then run the post-change smoke through an existing
healthy editor and confirm that a lifecycle recovery returns the compact final
verdict without manual journal inspection.

## Risks and Non-goals

- This does not broaden the Unity operation surface or change product test
  semantics.
- This does not make shell/source-only tests equivalent to live Unity proof.
- The stale-negative recheck can add bounded time for affected projects; it is
  intentionally limited to a decision that would otherwise weaken the lane.
- Consumer-specific smoke scenarios, editor processes, and product regressions
  remain outside this public plan.

## Next Step

Keep the deferred stale-negative and launcher-runtime slices separate from this
completed portfolio-evidence change. Before a release claim, run a
representative live Unity GUI fallback matrix and feed its persisted result
directory into the GUI subset runner.
