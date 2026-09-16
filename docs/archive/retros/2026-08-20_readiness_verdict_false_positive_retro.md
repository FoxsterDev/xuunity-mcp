# MCP Retro — `interactive_compile_block_detected` Asserts A Compile Fact Nothing Measured

Date: `2026-08-20`
Status: `P0, both P1 items, and the P2 heuristic item implemented in current source; P2 side-effect notice remains open`
Session shape: a long Unity feature-implementation session (compile + EditMode + PlayMode + portfolio batch matrix, no scenario runs), driven entirely through the MCP wrapper and tools.

## 1. Executive summary

The Unity side never failed. Every compile, test run and batch matrix in this session executed and reported truthfully. The failures were **readiness verdicts**: the wrapper returned `interactive_compile_block_detected` — whose message states *"Compilation errors were detected during interactive startup"* — **three times on a tree that had no compilation errors**, and it returned that same code for at least three *different* underlying states, none of which was a compile failure.

Worse, one of those verdicts led to a **destructive recovery**: acting on it ran `recover-editor-session`, which closed a healthy editor and cost a full reopen cycle. A false readiness verdict that recommends `recover_editor_session` is not a cosmetic wording bug; it converts a non-problem into an editor restart.

A second, independent heuristic in the same family also misfired: `editor_log_diagnosis.code = "api_updater_activity_observed"` warned that an interactive open "may be blocked on the API Update Required dialog", and its only cited evidence line was `-accept-apiupdate` — the launch flag whose entire purpose is to prevent that dialog. The heuristic matched on the cure and reported the disease.

The third finding is about the operator, and it is the reason this retro exists in this shape: an initial write-up of this session listed **seven** "MCP gotchas". On re-check only **three** were tool defects; three were operator error and one was not a problem at all. The wrapper's self-contradicting payload actively invites that inflation, so the mitigation is partly product and partly a classification rule.

## 2. Evidence base

- Three `interactive_compile_block_detected` payloads returned by the wrapper (`ensure-ready --open-editor`, `ensure-ready`, and a `unity.project.refresh` call).
- Immediately-following `unity.compile.player_scripts` results for the same tree: `post_settle_compile: "passed"`, `post_settle_error_count: 0`, `post_settle_script_compilation_failed: false`, `post_settle_compile_trust_class: "confirmed"`.
- `bridge_state.json` identity fields across the session: `bridge_generation` 1184 → 1186 → 1191 → 1195 → 1204 → 1206, with `bridge_pid` changing (45216 → 10604 → 21035 → 57295 → 63487).
- `host_prerequisites` blocks inside the failing payloads.
- `editor_log_diagnosis` blocks including the `api_updater_activity_observed` case and its `evidence_lines`.
- Batch matrix aggregate summaries (three full 12-project runs), each `projects_failed: 0`, `projects_blocked: 0`, `passed_via_batch: 12`.
- Interactive result accounting for EditMode (483/483) and PlayMode (30/30) runs.

## 3. Timeline

1. `ensure-ready --open-editor` → exit code 0 but `request_failure code=interactive_compile_block_detected`. Payload simultaneously reported `host_health_classification: "fresh"`, bridge `health_status: "healthy"`, `host_prerequisites.ready: true`, `blocking_codes: []`, and a live editor pid.
2. `unity.health.probe` → `status: "healthy"`. `unity.compile.player_scripts { target: iOS }` → passed, 0 errors, `confirmed`. **The first verdict was false.**
3. Mid-session, a tool call returned the same code with `host_health_classification: "stale"`, `reconciliation_case: "stale_bridge_state"`, and a **changed editor pid**. The real condition was a bridge/pid mismatch after the editor was replaced — again not a compile failure. Acting on the recommendation ran `recover-editor-session`, which closed the editor.
4. Reopening produced the code a second time while `is_updating: true` — i.e. the editor was still importing. `unity.project.refresh` immediately afterwards → passed, 0 errors.
5. After the portfolio matrix (which closes live editors by design), a `unity.project.refresh` returned the code a third time with `host_health_reason: "live_editor_without_live_bridge_state"` and `bridge_bootstrap_attached: false` — the editor was mid-boot. Polling `bridge_bootstrap_attached` then refreshing worked first try.
6. Every subsequent compile/test/matrix result in the session was truthful and needed no second opinion.

## 4. What worked well

- **Unity-side execution stability was total.** Three 12-project batch matrices, two platform compiles repeated many times, 483 EditMode tests and 30 PlayMode tests — zero flakes, zero disagreements between runs.
- **Result accounting is trustworthy and cheap.** `post_settle_compile` + `post_settle_error_count` + `post_settle_compile_trust_class: "confirmed"` was correct every single time and is the field set that let the false verdicts be disproven in one call.
- **The batch matrix summary surface is excellent.** One line per project plus an aggregate `{projects_total, projects_failed, projects_blocked, operator_verdict_counts}` made a 12-project verdict readable without opening a single per-project result file.
- **Fail-fast argument validation.** A call missing a required argument returned the field name, the expected form, and `Nothing was executed`. No side effect, no ambiguity.
- **Anchored log search was honest this time.** `log_lane`, `since_anchor.anchored` and `scope_truncated: false` together let a **zero-match result be trusted as a real negative** — the exact opposite of the failure mode filed in the previous retro. When those fields are populated, the tool is good at proving absence.

## 5. What worked poorly

- **One error code stands for several unrelated states.** `interactive_compile_block_detected` was returned for (a) a healthy editor with a clean tree, (b) a replaced editor pid / stale bridge state, and (c) an editor still booting with the bridge not yet attached. Only one of those three is even in the neighbourhood of "compilation errors".
- **The message asserts a measurement that never happened.** "Compilation errors were detected" was emitted without any compile having run in that request. A readiness gate may legitimately refuse to wait; it must not report a compile result it did not obtain.
- **The verdict contradicts its own payload.** `host_prerequisites.ready: true` with `blocking_codes: []` sitting inside a payload whose top level is a blocking error is not something an operator can reconcile.
- **The recommended action is destructive.** `recommended_next_action: "recover_editor_session"` on a false positive closes a healthy editor. Cost in this session: one editor restart plus the re-attach wait.
- **The API-updater heuristic matched on its own cure.** Citing `-accept-apiupdate` as evidence that the API-update dialog may be blocking startup is a straightforward inversion.

## 6. What was not explicit enough

- Nothing in the payload distinguishes *"the wrapper chose not to wait"* from *"Unity reported a compile failure"*. Those are different facts with different remediations and they currently share a code.
- `editor_log_diagnosis` does not carry a confidence or a "heuristic, may be a false positive" marker, even when its `freshness_class` is already `unverified_live_editor_session` and `reflects_current_working_tree: false` — two fields that, in the API-updater case, were the actual reason the diagnosis should have been discounted.
- The batch matrix's editor-closing behaviour is documented in `--help` but not surfaced in the wrapper output at the moment it closes an editor, which is when an operator mid-session would notice.

## 7. What the operator needed but did not have

1. A code that names the real condition: `editor_not_ready_bridge_not_attached`, `editor_identity_changed`, `editor_busy_importing` — instead of one compile-flavoured catch-all.
2. A non-destructive first recommendation for the not-yet-ready case: poll `bridge_bootstrap_attached`, do not close the editor.
3. An explicit `compile_state: "unmeasured"` (or absence of the field) so the payload cannot look like a compile verdict when no compile ran.
4. A heuristic-confidence marker on `editor_log_diagnosis`, so an unverified prior-session inference is visibly weaker than a measured result.

## 8. Scoring

| Category | Score | Note |
|---|---|---|
| Unity-side execution stability | 10/10 | Zero failures across 3 matrices, many compiles, 513 tests |
| Request journaling quality | 9/10 | Journal + request ids consistently present and correlatable |
| Bridge health observability | 8/10 | Rich identity fields; they are what disproved the verdicts. Point off because the verdict ignored its own fields |
| Wrapper-to-operator clarity | **4/10** | One code for three states, asserting an unmeasured fact, contradicting its own prerequisites block |
| Recovery guidance quality | **4/10** | Recommended a destructive recovery for a non-problem |
| Transport lifecycle transparency | 8/10 | Generation/pid churn was visible and explicable after the fact |
| End-to-end trustworthiness during churn | 6/10 | Results were trustworthy; readiness verdicts were not |
| Parallel request handling | 9/10 | Matrix at `--parallelism 4` clean three times |
| Token efficiency of the default operator path | 6/10 | Each false verdict returned a ~6–8 KB payload; compact summaries elsewhere were excellent |
| Time-to-diagnosis | 7/10 | One compile call disproves the verdict — but only if you already distrust it |
| Validation workflow discipline | 8/10 | Compile-first ordering held; matrix correctly run last |

## 9. Priority improvements

- **P0 — split the code and stop asserting an unmeasured compile.** Return a condition-specific code (`bridge_not_attached`, `editor_identity_changed`, `editor_busy_importing`, `compile_errors_detected`) and only use the last one when a compile actually reported errors. Keep the fail-fast behaviour; change the claim.
- **P1 — make the recommendation non-destructive by default.** For not-ready-yet states recommend polling `bridge_bootstrap_attached`; reserve `recover_editor_session` for a proven-stuck or identity-mismatched session.
- **P1 — refuse to emit a blocking verdict that contradicts `host_prerequisites.ready: true`.** If the prerequisites block says ready with no blocking codes, the top-level result must not be a blocking error; that pairing is an internal inconsistency and is worth an acceptance check.
- **P2 — mark heuristic log diagnoses as heuristic**, and suppress `api_updater_activity_observed` when the cited evidence is `-accept-apiupdate` itself.
- **P2 — echo destructive side effects in wrapper output**: when the batch runner closes a live editor, say so in the summary, not only in `--help`.

## 10. Public-promotion recommendations

- `README.md` / `docs/operations/CONTINUATION.md`: add an operator rule — **a readiness verdict is not a compile verdict**; confirm with `unity.compile.player_scripts` before believing a tree is broken or running a recovery.
- `docs/operations/SMOKE_TESTS.md`: add an acceptance check that a payload with `host_prerequisites.ready: true` and empty `blocking_codes` never carries a top-level blocking error, and that `interactive_compile_block_detected` is only produced when a compile actually reported errors.
- `docs/architecture/ROADMAP.md`: record the error-code split as a small, self-contained slice.
- **Reusable operator rule worth promoting beyond this tool:** classify before filing. In this session an initial list of seven "tool problems" resolved to three tool defects, three operator errors (a required argument not read, a documented default not respected, a harness rule mistaken for an MCP rule) and one non-problem. A payload that contradicts itself makes inflation the default, so the counter-discipline is to attribute each item explicitly before writing it down as a product defect.

## 11. Final verdict

**PASS with one product fix worth shipping.** The measurement surfaces of this tool — compile accounting, test accounting, batch summaries, anchored log search with its lane/anchor/truncation fields — were accurate and cheap throughout a long, heavy session, and they are what made the bad verdicts falsifiable in a single call. The defect is narrow and entirely in the readiness gate: one overloaded error code that asserts a compile fact nothing measured, contradicts its own prerequisites block, and recommends closing a healthy editor. Fixing the code split and the recommendation removes the only class of failure this session actually suffered.

## 12. Implementation closeout — 2026-08-20

Current source closes the P0 and both P1 items as one readiness-truth slice:

- log observations no longer become compile verdicts; readiness failures carry
  condition-specific codes and `compile_state: "unmeasured"`
- bridge attach, import/compile busy state, and editor-identity churn keep
  polling inside the readiness budget and use non-destructive recovery when the
  condition persists
- enriched error payloads add a matching blocking readiness-gate prerequisite,
  preventing a top-level blocking error from carrying `ready: true` with no
  blocking code

Focused host coverage includes each condition, prerequisite alignment, recovery
command mapping, and the stale-log race where a bridge attaches on the next
poll; the full host suite also passes. Live regression passed package
EditMode/PlayMode tests on a Unity 2022 consumer and the full compile, scenario,
contract, PlayMode-lifecycle, churn, and project-action suite on a Unity 6000 consumer. The Unity 6000 startup run
also reproduced the old-log/new-bridge race and then passed readiness after the
bridge attached, directly proving the wait no longer returns the false verdict.

The explicit wrapper notice when a batch lane closes an editor remains open.

## 13. Heuristic diagnosis closeout — 2026-09-16

Editor-log diagnoses now expose `diagnosis_confidence=heuristic` and
`diagnosis_basis=editor_log_pattern_match`. The literal `-accept-apiupdate`
launch flag is no longer an API Updater activity pattern, while real
`[API Updater]`, `API Update Required`, and `UnityUpgradable` evidence remains
detectable. Regression coverage proves both the flag-only negative and the
real-marker-plus-flag positive, so the cure is no longer reported as the
disease.
