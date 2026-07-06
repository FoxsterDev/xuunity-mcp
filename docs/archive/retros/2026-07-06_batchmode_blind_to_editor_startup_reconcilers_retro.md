# XUUnity Light Unity MCP Retro: Batchmode Is Blind to Editor-Startup Reconcilers, and Offline-Probe Diagnosis Freshness

Date: `2026-07-06`
Status: `active public retro`

## Executive Summary

During an onboarding session that connected a shared package/infra graph to a
consumer project, the graph included an **editor `[InitializeOnLoad]` startup
reconciler** that resolves a `Resources`-loaded configuration via
`Resources.LoadAll<T>(path)` and throws when the count is not exactly one. The
consumer project did not yet own that config, so the reconciler threw
`Wrong count of configuration objects at path <...>` on **every editor-update
frame in the GUI**.

A headless `-batchmode -quit -accept-apiupdate` compile was **GREEN throughout**,
and `unity.compile.player_scripts` reported `0` errors — because the reconciler
early-returns under `Application.isBatchMode`, and player-scripts compile
excludes editor and test assemblies. **A green compile gate did not prove the GUI
editor was clean.** The distinction — batchmode/player compile does not *execute*
`[InitializeOnLoad]` / `RuntimeInitializeOnLoadMethod` / editor-update hooks — was
not surfaced by any tool or doc; it had to be reasoned out.

A second, independent issue: an early `unity.health.probe` against an **offline /
stale** bridge surfaced a **prior editor session's** `interactive_compile_block_detected`
(a precompiled test-dependency `CS0246`) as the headline `editor_log_diagnosis`,
with no qualifier that the diagnosis was derived from a prior session and **not
verified against the current working tree**. The cited compile block was already
resolved on disk. Only independent verification (comparing the on-disk
dependency against a known-good reference) avoided a wrong "still broken /
dependency missing" conclusion.

This is a companion to
`2026-07-06_first_open_6000_upgrade_apiupdate_modal_and_console_source_retro.md`.
That retro covered `console.grep source=console` false-empty *retrieval* after a
domain reload and the `-accept-apiupdate` modal deadlock. This retro covers a
different failure mode: batchmode/player compile does not *run* editor-startup
code paths at all, and an offline probe's diagnosis can reflect a stale prior
session.

Net: the MCP behaved reliably (stable execution, complete journaling, clean
`ensure-ready` recovery, compact `status_summary`, and — critically —
`console.grep source=editor_log` gave the decisive, eviction-proof verdict). No
wrong conclusion was reached, but trust depended on operator discipline in two
spots the surface could make explicit.

## Evidence Base

- Offline `unity.health.probe`: `editor_not_running`, `state_is_live=false`,
  `editor_pid_not_alive=true`, `heartbeat_age ~1000s`,
  `host_health_classification=offline`. Alongside it,
  `editor_log_diagnosis.code=interactive_compile_block_detected` with evidence
  lines from a **prior** host-opened session (`scope.source=host_opened_editor_session`,
  `fallback_used=false`) — presented without a "prior session / unverified vs
  current tree" qualifier.
- Working-tree counter-evidence: the cited precompiled test dependency was
  present on disk and byte-identical to a known-good reference (independent
  binary + import-settings comparison).
- Headless `-batchmode -quit -accept-apiupdate` compile: `0` `error CS`; the
  project's own assemblies compiled and were copied to
  `Library/ScriptAssemblies/`. The GUI-only reconciler exception did **not**
  appear (batchmode early-returns in the reconciler).
- GUI validation after the fix: `unity_status_summary` `compiler_error_count=0`,
  `script_compilation_failed=false`, `health_status=healthy`, idle.
  `unity_console_grep` `source=console` errors/exceptions `=0`; `source=editor_log`
  for the reconciler message `=0` (a broad entity-name pattern also matched benign
  `Start importing .../<path>/...` info lines — see below).
- `ensure-ready --open-editor --background-open --startup-policy fail_fast_on_interactive_compile_block`:
  recovered a healthy bridge with `editor_log_diagnosis={}`; the fail-fast policy
  did **not** false-fail (compile was genuinely green).
- Request journal over the session: complete lifecycle (`request_submitted` /
  `request_started` / `request_completed` balanced), many `bridge_bootstrap_attached`
  events across heavy asset-import/domain-reload churn, and `request_reclassified`
  events, with no lost requests.

## Timeline

1. Shared package/infra graph connected to the consumer project (adds an editor
   `[InitializeOnLoad]` config-sync reconciler).
2. GUI editor spams `Wrong count of configuration objects at path <...>` every
   editor-update frame.
3. `unity.health.probe` on the (now offline) bridge surfaces a **prior-session**
   compile block as the headline diagnosis.
4. Operator independently verifies the cited dependency is present and correct →
   discounts the stale diagnosis.
5. Root cause traced to the missing `Resources`-loaded config; fix authored.
6. Headless batchmode compile → `0` CS errors (but cannot exercise the GUI
   reconciler).
7. `ensure-ready` → GUI editor healthy; `status_summary` + `console.grep`
   (console + `editor_log`) → `0` reconciler exceptions. Fix confirmed **in the
   surface that reproduces the bug**.

## What Worked Well

- `console.grep source=editor_log` was the decisive, eviction-proof verdict for
  "did the editor-startup reconciler stop throwing" — the v0.3.36+ path-backed
  `editor_log` default paid off directly.
- Compact `unity_status_summary` gave decision-grade compile/idle truth at low
  token cost.
- `ensure-ready` (background-open + `fail_fast_on_interactive_compile_block`)
  recovered a healthy bridge cleanly and did not false-fail.
- Offline classification was honest about liveness (`state_is_live=false`,
  heartbeat age) and gave a recovery command.
- Journaling / bridge observability held through heavy import + domain-reload
  churn with balanced request lifecycle and no lost requests.

## What Worked Poorly

- `editor_log_diagnosis` on an **offline** probe presented a prior session's
  compile block as the headline diagnosis with no freshness qualifier — a
  false-red risk for "still broken / dependency missing."
- No surface or doc stated that a green batchmode/player compile does not
  exercise editor-startup runtime hooks, so "compile green" reads as "editor
  clean" unless the operator already knows the boundary.

## What Was Not Explicit Enough

- Batchmode and `unity.compile.player_scripts` do **not** run `[InitializeOnLoad]`,
  `RuntimeInitializeOnLoadMethod`, `EditorApplication.update`, or editor startup
  reconcilers, and player-scripts compile excludes editor + test assemblies →
  **green compile ≠ editor clean.**
- An `editor_log_diagnosis` on an offline/stale bridge reflects the **last**
  editor session's log, not the current working tree.
- On `source=editor_log`, grep matches are **untyped** — info/import lines match
  broad entity-name patterns; error-anchored patterns are needed. (Extends the
  companion retro's Console-vs-editor_log guidance to pattern selection.)

## What The Operator Needed But Did Not Have

- A documented **editor-startup-clean gate**: after a green compile gate — when
  the infra graph includes editor-startup hooks — open the GUI and grep
  `editor_log` for `Exception` / `error` before declaring the editor healthy.
- A **freshness qualifier** on `editor_log_diagnosis` when `state_is_live=false`
  (e.g. `derived_from=prior_session`, `reflects_current_working_tree=false`), so a
  stale `interactive_compile_block_detected` is not read as a current blocker.
- (Minor) `editor_log` grep guidance to anchor on error tokens rather than entity
  names.

## Scoring

| Category | Score | Notes |
| --- | ---: | --- |
| Unity-side execution stability | 9/10 | Unity did exactly what the assets dictated; the bug was a missing config, not instability. |
| Request journaling quality | 8/10 | Balanced lifecycle across heavy churn; no lost requests. |
| Bridge health observability | 7/10 | Accurate liveness; the offline `editor_log_diagnosis` lacked a freshness qualifier. |
| Wrapper-to-operator clarity | 6/10 | The stale offline diagnosis read as a current blocker. |
| Recovery guidance quality | 8/10 | Recovery command + `ensure-ready` worked, twice, no false-fail. |
| Transport lifecycle transparency | 8/10 | Generation / session id / listener state clear across churn. |
| End-to-end trustworthiness during churn | 8/10 | No false success; `editor_log` grep prevented a false-empty. |
| Parallel request handling | 8/10 | Concurrent greps completed cleanly. |
| Token efficiency of default path | 7/10 | `status_summary` compact good; `health_probe` full payload heavy for a liveness question. |
| Time-to-diagnosis | 7/10 | Fast, but the stale diagnosis risked a detour. |
| Validation workflow discipline | 7/10 | Compile-first + dual console/editor_log grep + GUI confirm; the batchmode-blind boundary was operator-supplied, not tool-surfaced. |

Overall: `83/110` (~`75/100`). A clean, reliable session; the two gaps are clarity/scope refinements, not failures.

## Priority Improvements

### P1: Document the compile-gate scope limit (green compile ≠ editor clean)
In `SMOKE_TESTS.md` (compile gate) and `AGENT_WORKFLOWS`, state that batchmode /
player-scripts compile does not execute `[InitializeOnLoad]` /
`RuntimeInitializeOnLoadMethod` / editor-update reconcilers and excludes
editor+test assemblies, and add an **editor-startup-clean gate** (GUI open +
`console.grep source=editor_log` for `Exception`/`error`) after the compile gate
when the infra graph adds editor-startup hooks.

### P1: Offline-probe `editor_log_diagnosis` freshness qualifier
When `state_is_live=false` / `editor_pid_not_alive`, tag `editor_log_diagnosis`
(and its evidence lines) as derived from a prior session and not verified against
the current working tree (`derived_from=prior_session`,
`reflects_current_working_tree=false`), so a stale
`interactive_compile_block_detected` is not read as a current blocker. Complements
the v0.3.36 editor-log-identity work (this is the offline-diagnosis nuance).

### P2: `editor_log` grep pattern guidance
Note in the grep docs that `source=editor_log` matches are untyped; prefer
error-anchored patterns (`error CS`, `Exception:`, exact message text) over
entity names when log presence of an *error* is the claim.

## Public-Promotion Recommendations

- `docs/operations/SMOKE_TESTS.md`: compile-gate scope-limit note + editor-startup
  -clean gate (added in this change).
- `docs/agents/AGENT_WORKFLOWS.md`: same boundary in the onboarding/first-connect
  workflow (green compile ≠ editor clean; validate editor-startup hooks in GUI).
- Wrapper/`health_probe` + `DESIGN`: offline-probe diagnosis freshness qualifier.
- Grep docs: `editor_log` untyped-match / error-anchored-pattern note.
- Keep all consumer-project specifics (paths, config names, SDK identities,
  dependency hashes) out of these public surfaces.

## Final Verdict

Unity ran correctly; the reported failure was a missing consumer-owned
`Resources` config that a shared editor `[InitializeOnLoad]` reconciler
hard-requires, and it was invisible to the compile gate because batchmode/player
compile never executes editor-startup hooks. The smallest durable fixes are
(1) document that a green compile gate does not prove editor-startup cleanliness
and add a GUI editor-startup-clean gate, and (2) qualify `editor_log_diagnosis`
freshness on offline probes so a prior-session compile block is not mistaken for
a current one.
