# XUUnity Light Unity MCP Chat Retro — Prefab/UI Authoring + Visual-Iteration Gap

Date: `2026-07-17`
Status: `active public retro — reliability slice implemented; authoring and mutation-delta follow-ups open`
Session type: presenter-driven Home-screen UI widget rework in a consumer Unity project (Unity `6000.0.58f2`), heavy prefab + localization + play-mode-screenshot iteration.

## 0. Grooming update — 2026-07-19

The smallest verdict-quality slice is implemented in current source:
`project_defined_hook_poll_until` now treats a passive `status: not_started`
payload as keep-waiting after evaluating explicit `passWhen` and `failWhen`.
Other unmatched statuses still fail closed, and timeout remains authoritative.
This prevents the demonstrated readiness false-negative without broadening the
predicate language or hiding explicit caller intent.

Validation is complete in current source: host regression passes `471` tests
with `13` expected platform skips; Unity `2022.3` package self-tests pass
EditMode `18/18` and PlayMode `5/5`; and a Unity `6000.0` consumer passes its
compile, scenario/contract, PlayMode lifecycle, final-health, and consistency
route.

The prefab structure-read/authoring/render capability remains open but is
ranked below verdict correctness under the reliability-first grooming rubric.
Mutation-delta safety also remains open as the stronger false-positive-success
follow-up from this retro.

## 1. Executive summary

The MCP was **reliable and trustworthy for every operation it exposes**: compile
gating, EditMode tests, console/editor-log grep, play-mode transitions, scenario
run-and-wait, and Game View screenshots all produced correct, low-false-negative
evidence. No Unity-side execution failure and no transport/bridge failure occurred
in the whole session.

The dominant friction was a **capability gap, not a reliability gap**: the task was
a UI rework (new background sprite + native sizing, four static progress-bar
markers, delete legacy objects, reposition elements), and the MCP has **no
prefab/scene authoring surface and no prefab-structure read surface**. The operator
was forced to (a) parse a ~1800-line prefab YAML by hand to learn the hierarchy and
serialized-field wiring, and (b) hand-author large prefab YAML blocks (a single
marker set was ~700 lines of GameObject/RectTransform/CanvasRenderer/Image/TMP
records with hand-assigned fileIDs). The **only visual feedback loop was a full
boot-to-lobby play-mode screenshot** (~30-45 s per cycle, and dependent on async
game data loading), because there is no "render this prefab/asset in isolation"
capability. This made every visual decision expensive and every hand-authored YAML
edit a break risk.

Two smaller, reusable operator-clarity issues also surfaced:
`project_defined_hook_poll_until` treats a passive hook `status: not_started` as a
terminal non-match (so a snapshot-style readiness poll fails instead of waiting),
and a mutating project action reported `catalog_built` success while silently
dropping rows (no before/after delta), which is a false-positive-success surface.

## 2. Evidence base

- Chat transcript / condensed timeline (this session).
- Wrapper-visible failures:
  - `scenario_invalid` from `unity_scenario_run_and_wait`, then `unity_scenario_validate`
    returned `missing_start_payload` and `invalid_fail_when` for a
    `project_defined_hook_poll_until` step.
  - `project_hook_poll_until_unmatched_status`: "poll payload status 'not_started'
    did not satisfy passWhen, failWhen, or continueWhen" for a passive
    `snapshot_flow` hook.
  - `maximize_quest_not_available` (product-assertion failure) at poll_count 1,
    `scene_name: SplashScreen`→`LobbyScene`, `before_reach_points: 0` — i.e. the
    smoke probed before async quest data loaded; a screenshot ~6 s later showed the
    data present and the widget fully rendered.
- Healthy-execution evidence:
  - `unity_project_refresh` → `post_settle_compile: passed`, `post_settle_error_count: 0`
    (used ~6× across code + prefab edits, always fast and correct).
  - `unity_tests_run_editmode` `assemblyNames:["HomeView.Tests"]` → `44/44 passed`
    (targeted filter selected correctly — the `2026-07-15` zero-match fix held).
  - `unity_console_grep` `source=editor_log` → `match_count:0` for exception and
    prefab-parse patterns after edits (no console-clear false negative).
  - `unity_status` → `stale_playmode_state_detected:true` +
    `recommended_next_action: exit_playmode_then_rerun_if_fresh_start_required`.
  - `unity_game_view_screenshot` `includeImage:true` → the decisive visual proof
    at each iteration.
- Bridge state: healthy throughout; `bridge_generation` advanced on each domain
  reload; transport `tcp_loopback` `listening` with no resets or churn.
- Public docs / contract: `CHAT_RETRO_PROMPT.md`, `RETRO_REGISTRY.md` (registry
  triaged against released source line `v0.3.47`).

## 3. Timeline (condensed)

1. `unity_status` → editor up, bridge healthy, `compiler_error_count:0`.
2. Code edits (model/view/presenter/DTO/localization) → `unity_project_refresh`
   compile gate `passed` each time.
3. `unity_tests_run_editmode` (HomeView.Tests) → `44/44`.
4. `unity_project_action_list` → chose `localization.build_blingz_catalog`;
   invoke reported `catalog_built` **but silently dropped 6 of 22 keys** (builder
   vs committed-catalog drift). Caught later by `git diff`, not by the tool.
5. First visual proof via `unity_scenario_run_and_wait` (enter → poll snapshot →
   screenshot); the first attempt was `scenario_invalid`, fixed after
   `unity_scenario_validate` explained the poll_until requirements.
6. Repeated boot→screenshot cycles to judge gradient, colors, timer pill, marker
   states, and overlap — each ~30-45 s, one blocked by async-quest timing.
7. Regressions I introduced were caught by the screenshot loop (panel overlap
   from a size change) and by `git diff` (dropped localization keys), then
   reverted/fixed.
8. Hand-authored 4 prefab markers (~700 lines YAML); `unity_project_refresh`
   compile + `unity_console_grep` parse-check both clean; screenshot confirmed
   render.

## 4. What worked well

- **Compile-first gate is excellent.** `unity_project_refresh` with a compact
  `post_settle_compile`/`post_settle_error_count` is the highest-trust, lowest-cost
  signal in the toolset; it caught nothing false and confirmed every edit fast.
- **Targeted EditMode filtering works** (`assemblyNames`) and returned a correct
  `44/44` with no zero-match artifact — the `2026-07-15` fix is holding.
- **`unity_console_grep source=editor_log`** reliably proved "no runtime
  exceptions" and "no prefab-parse errors" without console-clear false negatives.
- **`unity_scenario_validate`** turned an opaque `scenario_invalid` into two exact,
  actionable messages before wasting a play-mode run.
- **Compact scenario/refresh envelopes** kept per-call token cost reasonable; the
  `includeFullPayload` opt-in was never needed for these.
- **`game_view_screenshot includeImage:true`** is the single most valuable tool for
  UI work — it is what actually verified the design.
- **Stale-playmode detection** (`stale_playmode_state_detected` + a concrete
  recommended next action) prevented me from trusting a warm, pre-existing play
  session as a fresh boot.

## 5. What worked poorly

- **No prefab/UI authoring surface.** Every structural UI change (add container,
  add 4 markers with icon/label/checkmark + a component wired to serialized refs,
  swap a background sprite, resize, reposition, delete legacy objects) had to be
  done as raw-YAML edits. This is slow, and a single mistyped `fileID` silently
  breaks references with no compile error.
- **No prefab-structure read.** Understanding the target required paging a
  ~1800-line YAML file and reconstructing the hierarchy + serialized-field map by
  eye. `unity_scene_snapshot` exists for the active scene but not for an arbitrary
  prefab asset, and neither surfaces serialized fields / RectTransform values.
- **Visual iteration is boot-gated and data-timing-fragile.** The only way to see a
  UI change was a full boot-to-lobby screenshot (~30-45 s) whose content depended
  on async game data; there is no isolated prefab/canvas render. One validation
  produced a false `quest_not_available` purely because the probe ran before data
  arrived.
- **`poll_until` + passive snapshot hook is a trap.** A hook that always reports
  `status: not_started` (a read-only snapshot) is treated as *terminal* by
  `project_defined_hook_poll_until`, so the poll fails instead of continuing. The
  working shape (start-hook that reports `running`, plus `passWhen`/`failWhen` in
  `payload.<field> == 'value'` form, plus a required `startPayload`) had to be
  discovered by trial + `validate`.
- **Mutating project action gave false-positive success.** `localization.build_*`
  returned `catalog_built` with a total-count field but no delta vs the previous
  asset; it had dropped 6 keys. Only an out-of-band `git diff` revealed the
  regression.

## 6. What was not explicit enough

- The `project_defined_hook_poll_until` contract: that a hook's own `status` field
  gates termination, that `not_started` counts as terminal (not "keep waiting"),
  and that `startPayload` + a well-formed `failWhen` are mandatory. The
  `invalid_fail_when` message names the format but the `not_started`→terminal
  behavior is undocumented and surprising.
- That a mutating catalog/asset-builder project action **fully regenerates** its
  target and can drop pre-existing rows it does not know about — with no delta
  surfaced in the result.
- That reaching a data-dependent UI state after a fresh boot requires an explicit
  readiness wait; there is no "wait until the model/data predicate holds
  (tolerating not-yet-started)" primitive, so operators hand-roll fixed sleeps.

## 7. What the operator needed but did not have

1. A **prefab/asset structure read** (hierarchy + component list + serialized-field
   values + RectTransform), analogous to `unity_scene_snapshot` but for a prefab
   asset and including serialized fields — so authoring does not start with manual
   YAML archaeology.
2. A **prefab/scene authoring/mutation surface**: set serialized field, set
   RectTransform (anchors/pivot/size/pos), add/remove component, set `Image.sprite`
   / `TMP.text`, instantiate a child from a template, activate/deactivate, delete
   object — each addressed by a stable path or a returned handle, executed in-editor
   so fileIDs and references stay valid.
3. An **isolated prefab/Canvas render-to-screenshot** (render a prefab or a single
   Canvas subtree to an image without a full app boot) to collapse the ~40 s visual
   loop to seconds and remove async-data flakiness.
4. A **generic readiness-wait** that polls a project-hook/model predicate and
   tolerates `not_started` (keep-waiting) until pass/fail/timeout — the missing
   primitive behind both the poll_until trap and the async-data false negative.
5. **Mutation-delta safety** on mutating project actions (report added/removed/
   changed counts; warn on destructive drop) so a "success" is not silently a
   regression.

## 8. Scoring (x/10)

- Unity-side execution stability: **9** — compile/test/playmode/screenshot all correct, no execution failures.
- Request journaling quality: **8** — request ids + journal events consistent and legible.
- Bridge health observability: **8** — healthy throughout; stale-playmode flag valuable.
- Wrapper-to-operator clarity: **6** — scenario/validate errors clear; poll_until status semantics and mutation deltas were not.
- Recovery guidance quality: **6** — playmode `recommended_next_action` good; no guidance for poll_until-with-snapshot or async-data readiness.
- Transport lifecycle transparency: **8** — generation/session churn on domain reload was legible and non-disruptive.
- End-to-end trustworthiness during churn: **8** — no false-negative execution conclusions; the false negatives that occurred were product-timing and self-authored scenario shape.
- Parallel request handling: **7** — not stressed this session (serial validation).
- Token efficiency of the default operator path: **5** — compact envelopes good, but manual prefab-YAML read/author + repeated boot+screenshot dominated cost, and that cost is a missing-capability tax, not envelope bloat.
- Time-to-diagnosis: **7** — regressions were caught, but via out-of-band `git diff` and slow screenshots rather than a tool signal.
- Validation workflow discipline: **8** — compile-first → tests → console-grep → screenshot held cleanly.

## 9. Priority improvements (smallest reusable changes)

1. **P0 — Prefab/UI authoring + structure-read surface.** The single biggest lever
   for UI-editing sessions. Minimum viable: `unity_prefab_snapshot`
   (hierarchy + components + serialized fields + RectTransform) and a small typed
   mutation set (`set_serialized_field`, `set_rect_transform`, `add_component`,
   `set_image_sprite`, `set_tmp_text`, `instantiate_child_from_template`,
   `set_active`, `delete_object`) executed in-editor. Even read-only
   `unity_prefab_snapshot` alone removes the YAML-archaeology tax.
2. **P1 — Isolated prefab/Canvas render.** `unity_prefab_render` (or a Game-View
   render of one Canvas subtree) to a screenshot without a full boot, to make the
   visual loop seconds-fast and data-independent.
3. **P1 — Generic readiness-wait / poll_until fix.** Make
   `project_defined_hook_poll_until` treat `not_started` as keep-waiting (or add a
   `snapshot`-poll mode), and document the status-termination contract with a worked
   passive-readiness example.
4. **P2 — Mutation-delta safety for project actions.** Mutating actions (catalog/
   asset builders) should return added/removed/changed counts and warn on
   destructive drops; a rebuild that shrinks its output should not read as clean
   success.
5. **P2 — Data-readiness gate helper for boot-dependent UI smokes** (wait until a
   named model/data predicate holds before asserting), so play-mode UI proofs stop
   racing async loads.

## 10. Public-promotion recommendations

- `docs/architecture/ROADMAP.md` / `DESIGN.md`: add the **prefab/UI authoring +
  prefab-structure-read** capability and the **isolated prefab render** as a named
  roadmap theme (currently the toolset validates UI but cannot author or cheaply
  preview it).
- `docs/operations/SMOKE_TESTS.md` / scenario docs: document the
  `project_defined_hook_poll_until` **status-termination contract** (`not_started`
  is terminal today; `startPayload` + `payload.<field> == 'value'` `failWhen`
  required) with a passive-readiness example; and add a **data-readiness wait**
  pattern for boot-dependent UI smokes.
- Wrapper/runtime: mutating project actions emit an **object/row delta** and a
  destructive-drop warning in their compact result.
- `docs/operations/CONTINUATION.md`: reaffirm the validated fast path that worked —
  **compile-gate (refresh) → targeted EditMode → editor_log grep → boot+screenshot**
  — as the recommended UI-change validation order.

## 11. Final verdict

`stable-execution, capability-limited`. The MCP did not fail — it validated
faithfully and cheaply for everything it exposes, and the compile-first discipline
plus `editor_log` grep plus screenshot gave real confidence. The session's cost and
risk came from the **absence of prefab authoring, prefab structure-read, and
isolated prefab render**, which turned a UI rework into manual YAML surgery judged
only through a slow full-boot screenshot. Prioritize a prefab authoring +
structure-read surface (P0) and an isolated prefab render (P1); the poll_until
status contract, a readiness-wait primitive, and mutation-delta safety are small,
high-clarity follow-ups.
