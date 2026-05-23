# XUUnity MCP Devmode Batch Lifecycle Hardening Design

Date: `2026-05-23`
Status: `implemented; validated`

## Source

This plan came from the public-safe retro:

- `../../archive/retros/2026-05-23_devmode_batch_lifecycle_retro.md`

The retro showed four related operator-surface problems:

- package source-root resolution could select the wrong `templates/` root
- restricted process visibility could look like "editor is closed"
- quit acknowledgement was not clearly separated from process exit
- closed-editor batch conflict guidance did not tell the operator how to prove
  the editor was actually closed before rerunning batch

## Public Scope

Owner layer: public MCP wrapper/runtime/docs.

Public interfaces added or hardened:

- `verify-editor-closed --project-root PATH --timeout-ms N`
- `request-editor-quit --wait-for-exit --exit-timeout-ms N`
- `restore-editor-state --require-closed`
- process visibility fields:
  - `process_visibility_available`
  - `process_visibility_error_code`
  - `same_project_editor_closed`
  - `process_exit_verified`
  - `quit_request_accepted`
  - `closeout_classification`
  - `next_distinct_action`

## Implementation Status

Implemented:

- public wrapper resolves `Operations/XUUnityLightUnityMcp` before generic
  `AIRoot/templates`
- package-source preflight runs before `devmode` and `prodmode`
- host platform runtime reports process-listing availability and error code
- discovery reports `process_visibility_restricted` instead of
  `editor_not_running` when process listing is unavailable
- closed-editor verifier polls same-project Unity editor PIDs and fails
  explicitly when process visibility is restricted
- quit wait-for-exit path raises `editor_quit_ack_without_exit` when the
  request was accepted but the process remains live
- `restore-editor-state --require-closed` enforces same-project closure while
  preserving default backward compatibility
- batch conflict summaries recommend the wait-for-exit quit command and expose
  closeout verification fields
- compact error summaries surface process visibility and closeout truth
- macOS LaunchServices launch failures include Unity bundle/executable
  diagnostics without adding automatic executable fallback
- README, continuation, agent workflow, build automation, and feature docs
  describe the closed-editor batch recipe

Validation:

- `scripts/testing/run_host_python_tests.sh` passed 106 tests
- parser coverage added for new CLI flags
- process-listing failure coverage added
- wrapper source-root test added for fake `AIRoot/templates` plus
  `Operations/XUUnityLightUnityMcp`
- lifecycle coverage added for verifier, quit wait success/failure, and strict
  restore closeout

## Self-Review

What looked good:

- the implementation keeps `request-editor-quit` default behavior compatible and
  makes strict process-exit proof opt-in
- the same verifier is reused by direct verification, quit wait, restore strict
  mode, and batch guidance
- process visibility is now an explicit prerequisite for closed-editor truth
- wrapper source-root ambiguity is guarded before any manifest or lock mutation
- docs now tell the operator the exact recovery sequence instead of relying on
  inference

Risks and watch points:

- process listing still depends on host tools such as `ps` or PowerShell; future
  host clients should preserve the explicit restricted-state path
- `restore-editor-state` default remains backward-compatible, so callers that
  need closed-editor proof must opt into `--require-closed` or call
  `verify-editor-closed`
- no automatic termination was added for manually opened editors; this is
  intentional but requires clear operator follow-through
- live project validation was not part of this pass; the proof is host/runtime
  unit coverage plus shell-level wrapper coverage

Post-retro follow-up:

- keep new lifecycle fixes public-safe and generic
- update this design history whenever a retro-derived implementation plan lands
- continue separating "request accepted" from "operation/process verified" in
  future operator surfaces
