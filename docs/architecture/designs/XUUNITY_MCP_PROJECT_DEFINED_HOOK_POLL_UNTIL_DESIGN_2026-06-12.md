# XUUnity MCP Project-Defined Hook Poll-Until Design

Date: 2026-06-12
Status: implemented in `v0.3.29`; passive `not_started` continuation hardened in current source

## Goal

Add a first-class scenario operation for short, stable PlayMode UI smokes:
`project_defined_hook_poll_until`.

## Why P0

Current scenario JSON can run project-defined hooks, waits, screenshots, and cleanup,
but async UI flows need state-aware terminal waiting. Without this primitive, agents
fall back to fixed waits, repeated probe steps, and raw result inspection. That makes
small UI validation take tens of minutes instead of a three-minute operator loop.

## Operation Contract

The operation starts one project-defined hook action and then polls another action
until the hook payload reaches a terminal status.

Required fields:

```json
{
  "operation": "project_defined_hook_poll_until",
  "hookName": "example.ui_smoke",
  "startPayload": { "action": "start_flow" },
  "pollPayload": { "action": "snapshot_flow" },
  "passWhen": "payload.status == 'passed'",
  "failWhen": "payload.status == 'failed'",
  "continueWhen": "payload.status == 'running'",
  "intervalSeconds": 2,
  "timeoutSeconds": 180
}
```

Optional fields:

```json
{
  "promotePayloadFields": ["status", "failure_class", "selected_tab", "user_path"],
  "terminalScreenshot": true,
  "terminalConsoleTail": true,
  "continueToCleanupOnFail": true
}
```

## Terminal Semantics

- `passed`: scenario step passes and stores final payload
- `failed`: scenario step fails as product/setup/tooling based on `failure_class`
- `not_started`: keep polling by default for passive readiness snapshots; an
  explicit matching `passWhen` or `failWhen` still takes precedence
- timeout: scenario step fails with latest payload and timeout metadata
- cleanup: scenario runner must continue declared cleanup steps when configured

## Summary Semantics

Scenario summaries should promote:

- hook name
- terminal status
- failure class
- error code/message
- selected tab or visible screen
- user path
- before/after real UI values
- screenshot path
- cleanup result

## Implementation Notes

- Reuse existing `project_defined_hook` execution path for start and poll calls.
- Polling should happen inside the scenario runner so the host does not need to
  encode long ladders of wait/snapshot/assert steps.
- Predicate syntax can start with simple status equality before supporting a
  broader expression language.
- Large payloads should stay in raw result JSON; summaries should promote only
  compact scalar fields.

## Validation

Add a synthetic hook scenario that:

1. starts in `running`
2. returns `running` for at least two polls
3. returns `passed`
4. verifies compact summary promotion
5. verifies cleanup after a synthetic `failed` terminal state
6. verifies timeout includes latest payload
7. verifies passive `not_started` payloads keep waiting, while an explicit
   `failWhen` for `not_started` remains terminal

Current-source evidence: package self-tests pass EditMode `18/18` and PlayMode
`5/5` on Unity `2022.3`; the two new poll cases persist the expected three-poll
pass and first-poll explicit failure. A Unity `6000.0` consumer also passes the
compile, acceptance, contract, PlayMode lifecycle, and final-health route.
