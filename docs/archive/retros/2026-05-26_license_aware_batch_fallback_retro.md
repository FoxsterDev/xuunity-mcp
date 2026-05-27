# License-Aware Batch Fallback Retro

Date: `2026-05-26`
Status: `post-implementation notes`

## What Was Implemented

- Added host `license-capabilities` and MCP `unity_license_capabilities`.
- Added license/batch probe cache under `Library/XUUnityLightMcp/state/`.
- Added `--batch-fallback-mode auto|off|require-batch` to public batch helpers.
- Added GUI fallback mappings for compile, compile matrix, build-config matrix,
  EditMode tests, and player build.
- Added Unity-side `unity.build_player` and host `request-build-player`.
- Added structured lane, license, start-state, restore-state, and next-action
  fields to batch output.
- Updated public docs and design history.

## What Went Well

- Existing closeout hardening gave the fallback a clear safety boundary:
  process visibility, same-project PID proof, and verified restore state.
- The implementation could keep batch command UX stable while making default
  behavior safer for hosts where Unity batchmode is blocked.
- Focused tests caught parser/schema and preflight behavior without needing a
  live Unity editor for every case.

## Risks

- License wording changes can move a real blocker into
  `unknown_batch_failure`; this intentionally avoids unsafe fallback but may need
  future classifier updates.
- GUI fallback is only as safe as idle-state detection and closeout proof. It
  must continue to fail closed when process visibility is restricted.
- `unity.build_player` is intentionally plain. Complex product build pipelines
  still need project-defined hooks or build-config adapters.

## Follow-Up

- Run the full host Python test runner after docs/code closeout.
- Extend and run the Unity version matrix with license fields.
- Run a live GUI fallback smoke with a controlled batchmode-blocked probe.
- Collect additional Unity licensing log snippets across Personal, Pro, Build
  Server, and headless/Hub failure modes.
