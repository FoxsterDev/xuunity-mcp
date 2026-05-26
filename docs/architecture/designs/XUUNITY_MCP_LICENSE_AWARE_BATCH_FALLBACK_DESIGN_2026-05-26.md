# XUUnity MCP License-Aware Batch Fallback Design

Date: `2026-05-26`
Status: `implemented; host validated`
Owner layer: public host wrapper/runtime and Unity editor package

## Summary

Batch helpers now treat Unity batchmode as a capability that must be proven for
the current editor, project, license, and host session. When real batchmode is
blocked by known license/Hub/headless signals and GUI fallback is viable, public
`batch-*` commands can run the equivalent GUI bridge operation and report the
lane change explicitly.

## Public Interfaces

- Host CLI:
  - `license-capabilities --project-root PATH [--unity-app PATH] [--refresh] [--timeout-ms N]`
  - `request-build-player --project-root PATH --build-target TARGET [...]`
  - `batch-* --batch-fallback-mode auto|off|require-batch`
- MCP tools:
  - `xuunity_license_capabilities`
  - `unity_build_player`
- Unity bridge operation:
  - `unity.build_player`

## Capability Fields

`license-capabilities` reports:

- `unity_version`
- `editor_path`
- `license_kind_inferred`
- `batchmode_supported`
- `editor_ui_supported`
- `batchmode_blocker_code`
- `batchmode_probe_log_path`
- `recommended_execution_lane`
- `source_evidence`

Batch summaries add:

- `requested_execution_lane`
- `effective_execution_lane`
- `lane_fallback_reason`
- `license_batchmode_supported`
- `license_blocker_code`
- `start_editor_state`
- `restore_editor_state`
- `gui_fallback_log_path`
- `next_distinct_action`

## Implementation Checklist

- [x] Add shared license/batch probe and cache in host runtime.
- [x] Normalize known license/Hub/headless blocker logs.
- [x] Add `license-capabilities` CLI and `xuunity_license_capabilities` MCP tool.
- [x] Add `--batch-fallback-mode` to public batch commands.
- [x] Route compile, compile matrix, build-config matrix, EditMode tests, and
      player build through GUI equivalents when safe.
- [x] Add Unity-side `unity.build_player` operation for GUI player-build fallback.
- [x] Add structured lane fields to batch payloads and summaries.
- [x] Update README, build automation docs, feature inventory, status, workflows,
      changelog, and design history.

## Validation Evidence

Host validation passed:

```text
scripts/testing/run_host_python_tests.sh
133 tests passed
```

Focused parser/preflight/setup validation also passed during implementation.
Live Unity matrix validation remains follow-up evidence for installed-editor
license behavior.

## Self Review

What looks solid:

- Batch lane selection is centralized in the host runtime instead of duplicated
  across individual commands.
- Unknown batch probe failures do not automatically become GUI fallback; they
  remain diagnostic so compile errors or non-license failures do not get masked.
- GUI fallback refuses open-editor reuse unless the bridge state is idle in Edit
  Mode and fails closed when host process visibility is restricted.
- Player build fallback uses a dedicated bridge operation and records
  `validation_evidence=unity_gui`.

Risks:

- The license probe is deliberately pattern-based; new Unity licensing messages
  may classify as `unknown_batch_failure` until added.
- GUI fallback restore depends on the existing host-opened editor session
  closeout machinery and host process visibility.
- `unity.build_player` mirrors the plain batch build contract but is not a full
  project-specific build system; custom build profiles still need project hooks
  or adapters.

## Post-Retro Notes

What went well:

- The prior process-visibility hardening made this pass smaller because the
  fallback could reuse verified editor closeout fields.
- Optional capability work made it natural to treat batchmode as another
  capability rather than a hard assumption.

Remaining follow-up:

- Extend the installed-editor matrix to record `batchmode_supported`,
  `license_blocker_code`, `effective_execution_lane`, and fallback result.
- Run a live GUI fallback smoke on a real project using a controlled
  batchmode-blocked probe.
- Add more license log snippets as Unity versions expose new wording.
