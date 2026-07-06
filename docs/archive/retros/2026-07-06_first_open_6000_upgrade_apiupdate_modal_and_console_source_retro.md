# XUUnity Light Unity MCP Retro: First-Open 6000 Upgrade — API-Updater Modal Stall & console_grep False-Empty

Date: `2026-07-06`
Status: `active public retro`

## Executive Summary

During the first MCP-driven open of a vendor Unity `2022.3.x` URP project migrated
to the hub-pinned `6000.0.58f2`, the GUI editor was launched **without
`-accept-apiupdate`**. The `2022 → 6000` upgrade contained a `UnityUpgradable`
rename (`PhysicMaterial` → `PhysicsMaterial`) in an editor script, so Unity
raised the modal **"API Update Required"** dialog on open. That modal froze the
editor main thread. The MCP bridge process stayed alive and its heartbeat file
stayed present, but the heartbeat age climbed (181s → 480s) because the main
thread could not pump.

This was **not** a Unity execution failure and **not** a transport failure. It
was an interactive-modal deadlock that the wrapper described accurately as
"stale with progress evidence / observe_only" but never named as a likely
**blocking dialog** with a concrete recovery.

Two secondary problems compounded diagnosis: (1) `unity.console.grep` on the
default `source=console` returned **0 matches** for the compile errors (the
console ring buffer had been cleared by domain reload), so the real `error CS`
lines were only visible by grepping the raw `-logFile`; (2) the reliable path
turned out to be a headless `-batchmode -quit -accept-apiupdate` run, which
applied API updates with no modal, compiled, exited, and left a greppable log.

## Evidence Base

- `unity.project.refresh` → `editor_idle_timeout`:
  `busy_reason=package_operation`, `busy_reason_detail=Client.Resolve:resolve_requested`,
  `refresh_settle_pending=true`, `is_compiling=true`, `asset_import_in_progress=true`,
  `host_health_classification=stale`,
  `host_health_reason=prolonged_lifecycle_churn_with_progress_evidence`,
  `host_health_termination_policy=observe_only`,
  `host_health_recommended_next_action=none`,
  `host_health_heartbeat_age_seconds` rising 181 → 480.
- `unity.status` (`timeoutMs=120000`) → `transport_response_missing`
  ("TCP loopback transport closed before the request was observed"),
  `result_trust_class=request_not_observed`,
  `bridge_stabilization.blocking_reasons=[asset_import_in_progress,
  package_operation_in_progress, compile_broken, refresh_settle_pending]`,
  `safe_to_retry=false`.
- Raw `-logFile` (batchmode) showed the actual blockers:
  - `error CS0234: 'VisualScripting' does not exist in the namespace 'Unity'`
    (dead `using` after the Visual Scripting package was dropped)
  - `error CS0619: 'PhysicMaterial' is obsolete ... (UnityUpgradable) ->
    PhysicsMaterial` in a kept third-party editor script
  - `[ApiUpdater] ... 1 modified` / `[API Updater] Updated Files:` lines
- `unity.console.grep` `source=console`, `includeTypes=["error"]`,
  `pattern=CS[0-9]` → `match_count=0` while the editor log clearly held the
  `error CS` lines.
- Recovery evidence: headless `-batchmode -quit -accept-apiupdate` exited `0`
  with `Exiting batchmode successfully now!` and `0` `error CS`; a subsequent GUI
  reopen + `unity.playmode.set enter` reached `is_playing=true` and
  `unity.game_view.screenshot` captured a correctly-rendered frame with
  `unity.console.grep includeTypes=[error,exception]` `match_count=0`.
- Final `bridge_state.json`: `health_status=healthy`, `compiler_error_count=0`,
  `supported_operation_count=24`.

## Timeline

1. Vendor `2022.3.x` project imported and cleaned; manifest aligned to `6000`
   (URP 14 → 17, dropped Visual Scripting among dev/unused packages).
2. Headless `-batchmode -quit -accept-apiupdate` first pass: API updater fixed
   the runtime assembly (`PhysicMaterial` → `PhysicsMaterial`) but the run
   exited on the earlier `VisualScripting` `CS0234` errors before reaching the
   editor assembly.
3. Dead `using Unity.VisualScripting;` / `using UnityEditor;` removed and a
   `Transform.AddComponent<T>()` (a Visual Scripting extension) rewritten to
   `gameObject.AddComponent<T>()`.
4. GUI editor launched **without** `-accept-apiupdate` for Play Mode.
5. Editor raised the modal API-Update dialog on the still-obsolete editor-script
   `PhysicMaterial` → main thread frozen.
6. `unity.project.refresh` → `editor_idle_timeout`; `unity.status` →
   `transport_response_missing`; heartbeat age climbed to 480s.
7. Root cause found by grepping the raw editor `-logFile`, not via MCP console.
8. Editor killed by PID (target project only), obsolete API fixed on disk,
   headless `-accept-apiupdate` re-run → compile green.
9. GUI reopened → bridge healthy → Play Mode proven, screenshot captured, 0
   runtime errors.

## What Worked Well

- Request journal + `bridge_state.json` cleanly proved the editor process was
  alive and the transport listener was up, so the failure was correctly excluded
  from "Unity crashed" and "transport dead."
- Health classification was honest: `stale` + `prolonged_lifecycle_churn_with_progress_evidence`
  + `observe_only` correctly told the operator not to force-kill on a timeout.
- The headless `-batchmode -quit -accept-apiupdate` path was a reliable,
  notify-on-exit, greppable verdict source and became the trustworthy compile
  gate.
- `unity.game_view.screenshot` + `unity.console.grep` (errors) after Play Mode
  gave a clean, low-token proof of the offline core.

## What Worked Poorly

- The default GUI open path on a freshly-upgraded project is a trap: without
  `-accept-apiupdate` the API-Update modal deadlocks the main thread, and the
  bridge cannot dismiss an OS modal.
- `unity.console.grep source=console` returned false-empty for compile errors
  after a domain reload — the operator path that *should* surface compile errors
  silently returned nothing, pushing diagnosis to raw log grepping.
- The `editor_idle_timeout` and `transport_response_missing` envelopes were large
  lifecycle-JSON blobs; the actionable signal ("editor busy, observe") was buried.

## What Was Not Explicit Enough

- A stale heartbeat with `busy_reason=package_operation`/`refresh_settle_pending`
  on a just-upgraded project is a strong signature of a **blocking interactive
  modal** (API Updater / import), but nothing said so.
- `source=console` is unreliable across domain reloads / clear-on-play;
  `source=editor_log` is the correct default for compile-error retrieval, but the
  tool defaults to `console`.
- "Relaunch non-interactively with `-accept-apiupdate`" is the canonical recovery
  for an upgrade-open stall, but it was operator tribal knowledge, not surfaced.

## What The Operator Needed But Did Not Have

- A health hypothesis: "editor heartbeat stale under `package_operation` after a
  version upgrade — it may be blocked on an interactive dialog; relaunch with
  `-accept-apiupdate` (batchmode for a deterministic verdict)."
- A compile-error retrieval path that does not silently return empty after a
  reload (auto-fallback `console` → `editor_log`, or an explicit
  `source=console_may_be_stale` warning when the buffer was cleared).
- A documented first-open onboarding rule to always pass `-accept-apiupdate` when
  opening a project whose `ProjectVersion` was just raised.

## Scoring

| Category | Score | Notes |
| --- | ---: | --- |
| Unity-side execution stability | 8/10 | Once unblocked, compile + Play Mode were clean and correct. |
| Request journaling quality | 8/10 | Journals proved liveness and separated the modal stall from execution. |
| Bridge health observability | 7/10 | Heartbeat-age + churn were visible; the "modal block" hypothesis was missing. |
| Wrapper-to-operator clarity | 5/10 | Accurate but generic; the actionable cause (blocking dialog) was never named. |
| Recovery guidance quality | 5/10 | `observe_only` was right but offered no path; recovery was tribal knowledge. |
| Transport lifecycle transparency | 6/10 | `transport_response_missing` was honest but a large, alarming envelope for "editor busy." |
| End-to-end trustworthiness during churn | 6/10 | No false success; but false-empty console_grep risked a false "no errors." |
| Parallel request handling | 8/10 | Requests were serialized; not a factor here. |
| Token efficiency of default path | 4/10 | Large idle-timeout/transport envelopes + fallback to raw-log grep were expensive. |
| Time-to-diagnosis | 5/10 | Root cause required raw `-logFile` grep after MCP console returned empty. |
| Validation workflow discipline | 8/10 | Headless compile-first-then-GUI-playmode was the right discipline once adopted. |

Overall: `66/100`.

## Priority Improvements

### P0: Upgrade-open modal-block hypothesis in health output
When `ProjectVersion` changed recently (or `Editor.log` shows API Updater
activity) AND heartbeat is stale under `busy_reason=package_operation` /
`refresh_settle_pending` with no domain-reload progress, add
`host_health_reason=possible_interactive_dialog_block` and
`recommended_next_action=relaunch_noninteractive_accept_apiupdate`.

### P0: compile-error retrieval must not false-empty
`unity.console.grep` / `unity.console.tail` should auto-fall back to
`source=editor_log` (or emit a `console_buffer_cleared` warning) when the console
buffer was cleared by a domain reload / clear-on-play, so an empty error result
is never mistaken for "no compile errors."

### P1: First-open onboarding profile passes `-accept-apiupdate`
`ensure-ready --open-editor` (and documented first-open commands) should pass
`-accept-apiupdate` by default when the target `ProjectVersion` was just raised,
so the API Updater applies headlessly instead of raising a modal.

### P1: Compact envelope for idle-timeout / transport-missing
Reduce `editor_idle_timeout` and `transport_response_missing` to a compact
default (classification + heartbeat age + blocking_reasons + one recommended
action), with `includeFullPayload=true` opt-in. (Aligns with the existing
token-efficiency / response-envelope backlog.)

### P2: "batchmode verdict first" documented as the upgrade compile gate
Promote the pattern: on a version upgrade, run
`-batchmode -quit -accept-apiupdate` for a deterministic, notify-on-exit,
greppable compile verdict before opening the GUI for interactive Play Mode.

## Public-Promotion Recommendations

- Docs/`AGENT_WORKFLOWS`: "first open after a Unity version upgrade" section —
  always `-accept-apiupdate`; batchmode compile gate before GUI Play Mode.
- Wrapper/runtime: modal-block hypothesis + recommended action in health output.
- Tool behavior: `console.grep`/`console.tail` fallback to `editor_log` on a
  cleared buffer.
- Smoke/validation order: compile (headless, accept-apiupdate) → GUI Play Mode.
- Acceptance check: a stale-heartbeat-under-package-operation regression fixture
  that asserts the modal-block hypothesis + recovery action are emitted.

## Final Verdict

Unity ran the project correctly; the failure was an interactive API-Update modal
deadlock on a version-upgrade first-open, made hard to diagnose because the
default compile-error console path returned empty after a domain reload. The
smallest durable fixes are (1) name the modal-block hypothesis with a concrete
`-accept-apiupdate` recovery in health output, and (2) never let
`console.grep`/`console.tail` return a false-empty compile-error result across a
reload.
