# XUUnity Light Unity MCP Retro: Manual-Open Editor Duplicate Launch

Date: `2026-06-18`
Status: `active public retro; implementation started`

## Executive Summary

During same-host validation, the host wrapper attempted to launch Unity for a
project that was already open manually. Unity showed the duplicate-project
modal: another Unity instance was already running with the same project open.

This was not a Unity compile, EditMode, or PlayMode failure. It was an MCP host
lifecycle failure: activation trusted bridge/transport readiness too strongly
and did not treat a same-project Unity process as a hard launch blocker before
calling the editor open path.

The operator impact was high. A validation run that should have reused or waited
for the existing editor instead created an OS-level modal that the bridge cannot
dismiss and the human had to close.

## Evidence Base

- Wrapper output from the affected validation path reported:
  - `reconciliation_case=host_launchable_not_active`
  - `reconciliation_status=offline`
  - `action=opened_editor`
  - `launch_command=["open", "-na", "...Unity.app", "--args", "-projectPath", "<ProjectRoot>", ...]`
- The same activation result later showed a healthy bridge attached to the same
  project and successful Unity-side operations.
- Request journal evidence after activation showed successful operations:
  - `unity.compile.player_scripts` request `481872e6-18c4-410b-8e4e-d81df5c28619`
  - `unity.tests.run_editmode` request `1232976b-dd8f-46df-87fc-ead2c6846c3c`
- Current status after operator recovery reports:
  - `editor_running=true`
  - `mcp_reachable=true`
  - `reconciliation_case=bridge_state_authoritative`
  - `host_prerequisites.live_editor.status=ready`
  - `detected_editor_pids` includes the main editor plus Unity asset import
    worker processes.
- A screenshot confirmed the Unity modal: multiple Unity instances cannot open
  the same project.

Important evidence gap: after the operator closed the duplicate bit instance,
the original pre-modal process list was no longer available. The retro therefore
does not claim the exact pre-existing PID. The wrapper-visible failure is still
clear: it chose an editor open path without first proving same-project process
absence.

## Timeline

1. The agent launched MCP validation commands for the same project.
2. The wrapper saw no trusted live bridge identity at activation start
   (`bridge_generation=0`, empty session before the request).
3. Activation classified the project as `host_launchable_not_active`.
4. Because the command allowed activation/opening, the wrapper invoked Unity via
   the host open path.
5. A same-project Unity instance was already open manually or was still opening.
6. Unity displayed the duplicate-project modal.
7. The operator closed the extra bit instance manually.
8. The bridge later became healthy and the compile/EditMode operations
   themselves completed successfully.

## What Worked Well

- Request journals were enough to prove that Unity-side compile/test operations
  were not the product failure.
- Status summary after recovery made the current healthy editor state clear.
- The existing journal model preserved request ids and bridge generations, so
  the failure could be separated from the later successful operations.

## What Worked Poorly

- The activation path was bridge-first, not process-lock-first.
- `host_launchable_not_active` was allowed to progress to `open_editor` without
  a hard same-project process check.
- The wrapper did not print a compact "same-project Unity process already
  present; waiting/reusing instead of opening" message.
- The agent ran compile and EditMode validation in parallel, which is a poor
  lifecycle pattern for Unity editor activation. Even if per-request execution
  later serialized, activation pressure was unnecessary.
- The previous single-project launch safety retro covered launch-in-progress
  reuse, but this case shows manual-open editor detection was still not strict
  enough.

## What Was Not Explicit Enough

- A missing or stale bridge is not the same as a missing Unity editor process.
- `open -na` is unsafe when any same-project editor process is visible.
- Asset import worker processes must not count as the main editor, but a main
  Unity process with the same `-projectPath` must block launch.
- When same-host validation needs the editor, the safe order is:
  1. inspect process visibility
  2. inspect bridge state
  3. try to attach/reuse/wait
  4. only open if same-project process absence is proven

## What The Operator Needed But Did Not Have

- A clear pre-launch guard message explaining whether a same-project Unity
  process was already present.
- A fail-closed activation result instead of an automatic open when bridge state
  was absent but process visibility could not prove project absence.
- A recommendation such as: "Unity is already open without a reachable bridge;
  focus it or run ensure-ready/recover, do not open another instance."
- Agent guidance to avoid parallel activation requests against one Unity
  project.

## Scoring

| Category | Score | Notes |
| --- | ---: | --- |
| Unity-side execution stability | 8/10 | Compile and EditMode operations later completed successfully. |
| Request journaling quality | 8/10 | Journals proved operation outcomes, but not the pre-modal process list. |
| Bridge health observability | 8/10 | Current bridge health is clear; absent-bridge startup state was overtrusted. |
| Wrapper-to-operator clarity | 5/10 | The user saw an OS modal instead of a safe reuse/wait/fail-closed message. |
| Recovery guidance quality | 6/10 | Recovery after modal was possible, but the wrapper caused the modal. |
| Transport lifecycle transparency | 7/10 | Bridge generation/session were visible, but process-first launch safety was weak. |
| End-to-end trustworthiness during churn | 6/10 | Successful operations were real, but activation created avoidable churn. |
| Parallel request handling | 5/10 | Parallel activation pressure contributed to the bad operator experience. |
| Token efficiency of default path | 6/10 | Diagnosis still required large lifecycle envelopes and manual journal checks. |
| Time-to-diagnosis | 7/10 | The `opened_editor` evidence was visible, but not summarized as the root issue. |
| Validation workflow discipline | 6/10 | The agent should have serialized activation-heavy Unity requests. |

Overall: `68/100`.

## Priority Improvements

### P0: Process-Lock-First Launch Guard

Before any host editor open path, run a same-project main-editor process probe.
If a main Unity process already has the same canonical `-projectPath`, do not
call `open -na`.

Expected behavior:

- if bridge is reachable: reuse it
- if bridge is not reachable but same-project editor exists: wait/attach/recover
- if process visibility is restricted: fail closed with
  `process_visibility_restricted_before_open`
- if no same-project editor exists: open editor

### P0: Manual-Open Editor Classification

Add a distinct reconciliation case:

`same_project_editor_running_bridge_not_ready`

This should be different from `host_launchable_not_active`. The recommended
next action should be `wait_for_bridge_or_recover_editor`, not `open_editor`.

### P1: Main Editor vs Worker Process Classification

Process visibility should classify:

- main Unity editor process for project
- Unity asset import workers for project
- shader compiler/package manager children

Only the main editor process should block launch, but worker-only visibility
should be reported explicitly.

### P1: Per-Project Activation Single-Flight

Activation/open/recovery should be a per-project single-flight section even when
two host requests start concurrently. The second request should wait for the
first activation result rather than performing its own launch decision.

### P1: Agent Workflow Rule

Agent-facing docs should say: do not start multiple activation-heavy Unity MCP
commands in parallel for the same project. Serialize `ensure-ready`, compile,
tests, PlayMode, and scenario start until the bridge is healthy.

### P2: Compact Launch Decision Summary

Every activation that considers opening Unity should print a small launch
decision summary:

- bridge ready?
- process visibility available?
- main same-project editor pids?
- worker pids?
- selected action: reuse, wait, recover, open, or fail closed
- reason

## Public-Promotion Recommendations

- Promote the process-lock-first rule into the public wrapper/runtime contract.
- Update operation docs to separate "no bridge" from "no editor".
- Add regression tests for:
  - same-project main editor visible + bridge missing => no open
  - process visibility restricted + bridge missing => fail closed
  - worker-only processes visible + bridge missing => open allowed after
    launch-in-progress check
  - parallel same-project activation requests => one activation decision
- Add agent guidance that same-project Unity MCP validation should serialize
  activation-heavy commands.

## Implementation Progress

Started `2026-06-18`.

Implemented:

- `open_unity_editor` now fails closed with
  `process_visibility_restricted_before_open` before any host editor open path
  when process visibility is unavailable.
- Discovery now reports
  `same_project_editor_running_bridge_not_ready` with
  `wait_for_bridge_or_recover_editor` when a same-project main editor process is
  visible but the bridge is not ready.
- Unity worker/helper processes are classified separately and surfaced as
  worker pids without counting as a live main editor.
- Agent workflow docs now tell agents to serialize activation-heavy commands for
  the same Unity project until the bridge is healthy.
- Regression coverage was added for process-visibility fail-closed behavior,
  manual-open/no-bridge reconciliation, and worker-only process classification.

Still visible follow-up:

- Audit direct CLI `ensure-ready --open-editor` / `open-editor` concurrency as a
  dedicated activation single-flight surface, beyond the existing per-project
  request lock used by mutating bridge operations.
- Expand the compact launch decision summary so every reuse, wait, recover,
  open, and fail-closed branch emits the same field set.

## Final Verdict

The bug was not that Unity could not run the validation. The bug was that the
host wrapper attempted to open a new editor from an "offline bridge" conclusion
without first proving that the project was not already open.

The smallest durable fix is to make same-project process detection a hard gate
before `open -na`, with a new manual-open/no-bridge reconciliation case and
single-flight activation per project.
