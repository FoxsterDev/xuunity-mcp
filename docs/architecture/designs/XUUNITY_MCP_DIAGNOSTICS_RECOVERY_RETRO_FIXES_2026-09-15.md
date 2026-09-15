# Diagnostics, Recovery Guidance and Journal Completeness

Date: `2026-09-15`
Status: `implemented; host and Unity EditMode validated; lifecycle proof bounded below`
Owner: MCP package, Python host and public XUUnity validation guidance.
Input: a host-private MCP pilot retrospective dated 2026-09-15. Its evidence,
consumer identities, paths and request records are deliberately not reproduced.

## Scope and Confirmed Defects

Confirmation means the pre-change source contains the stated failure mechanism.
It does not prove every causal attribution about the original pilot.

| ID | Confirmed problem and why | Implemented correction | Primary owner |
| --- | --- | --- | --- |
| M-1 / C-M01 | Pipeline diagnostics had no capture time or generation; the gate called them confirmed even after the named source changed. | Publish capture time/generation; classify changed, unavailable, undated or previous-generation evidence as stale; refresh once under the existing project lock, then require a confirmed clean post-settle verdict before dispatch. Fresh errors still refuse. | `server_bridge_compile_gate.py`, `server_batch_orchestrator.py`, compiler diagnostics/state/status C# |
| M-2 / C-M02 | Idle-timeout details omitted PID liveness and described the last busy snapshot as current; the wait could discard the dead process's state. | Preserve the snapshot; include liveness, frozen classification, busy detail/time and literal recovery command. A fresh live busy editor retains the existing timeout class. | `server_bridge_state.py` |
| M-3 / C-M04 | Curated wrapper help omitted supported recovery, build and project-hook commands. | Generate grouped help from argparse, including all 77 verbs and required flags, within 90 lines. | `server_launcher.py` |
| M-4 / C-M03 | Readiness hardcoded another ensure-ready invocation regardless of its selected next action. | Render the selected action through the shared command owner. Preserve the old `recovery_command` field and add the common alias. | `server_readiness_summary.py` |
| M-5 / C-M06 | Missing optional uGUI registration was reported as a missing package without checking dependency evidence. | Distinguish installed/declared-but-unregistered, absent and unreadable dependency state; fix the UI reader recommendation too. Stamp/invalidate cached probes by bridge generation. | `XUUnityLightMcpHealthProbe.cs`, capability models |
| M-6 / C-M03 | The compile gate's next-action spelling was absent from the command map. | Consolidate the renderer in `server_recovery_commands.py`; cover the demonstrated compile, readiness and idle recovery actions. Do not invent commands for unrelated unverified repair tokens. | recovery renderer and compile gate |
| M-7 / C-M05 | Compile/idle refusals before transport submission had no journal event. | Atomically write `request_refused`, with code, reason, operation, command and decision evidence; mark it unsubmitted with no fabricated request ID. | `server_bridge_journal.py`, orchestrator |
| M-8 / C-M05 | Completion journaling did not receive the response error, so the reason remained empty. | Pass synchronous and asynchronous terminal responses to the journal; retain the error message with code/status fallbacks. | request pump, journal, test/resolver completion owners |
| M-9 / C-M05 | Journal transport success did not expose the test verdict, allowing a zero-match result to look like a passing run. | Add `test_verdict` alongside transport/operation status. Do not rewrite successful delivery as transport failure. | journal event model and writer |
| M-10 / C-M07 | First package installation into an already-running editor produced no attachment warning. | Add affected roots and a conditional import/restart explanation to setup plan/apply, rechecking before application. | setup common/plan/apply |
| P2-8 | Missing or empty action catalogs gave no route to the existing hook scaffold. | Return a complete, quoted `project-hook-scaffold` command targeting project Temp. | `server_project_actions.py` |

## Observations That Are Not Separate MCP Defects

| Retro item | Assessment | Why it appeared, and resulting action |
| --- | --- | --- |
| M-11: many refresh requests | A workload metric, not proof that every refresh was caused by stale diagnostics. | It illustrates pilot overhead. M-1 and command discovery address demonstrated mechanisms; no unsupported attribution or arbitrary refresh throttling was added. |
| M-12: raw batchmode use | Operator routing gap; supported lanes already existed. | The pilot bypassed those lanes. Help and workflow guidance now surface them; no duplicate batch engine was built. |
| M-13: inline build and frozen heartbeat | Main-thread blocking can stop update-driven heartbeat and request processing. The specific crash/deletion cause remains unproven. | The retrospective correlated a long inline build, frozen state and a crash artifact. Guidance forbids long inline initialization work. A background-execution setting alone does not prove any particular callback ran. |
| M-14: unused evidence operations | Missing validation evidence, not missing capability. Empty directories alone cannot prove every operation was never invoked. | Scene/assertion/screenshot/scenario needs were not mapped to supported operations. Workflow guidance now requires that mapping and justified omissions. |
| M-15: missing build artifact | A historical build success is insufficient proof of a currently available deliverable; the cause of disappearance is unknown. | Handoff lacked current artifact verification. Public guidance requires a present, non-empty artifact and identity/size. No unsupported deletion fix was invented. |
| I-13/I-22: asking for editor restart | A bridge quit command cannot reach an editor without an attached bridge. Asking for out-of-band help can therefore be valid. | The original explanation was missing. The retro's stronger claim that restart is always the only remedy is not established: import/domain reload may attach the new package. Setup guidance states restart conditionally. |
| “Unity did not fail” | Too broad for the available evidence. | Reliable transport recovery is not proof that the editor never crashed. Preserve successful lifecycle/fallback behavior without asserting an unproved root cause. |
| C-M08/C-M09 | Their concrete phase gates belong to the separate workflow owner. | This MCP change promotes reusable discovery/main-thread/artifact rules into MCP agent docs and public XUUnity validation guidance. It does not claim implementation or replay of another module's phase gates. |

## Implementation Decisions

- C# editor callbacks remain on the existing editor thread; no new worker,
  polling loop, reflection shim or dependency was introduced. Existing locks
  and atomic file writers remain the owners of shared state and disk delivery.
- The captured timestamp marks the start of the compile cycle, conservatively
  detecting edits made while compilation was in progress. It is not a heartbeat.
- Recovery uses one private already-locked invocation. Re-entering the public
  invocation would reacquire a non-reentrant lock; a regression test detects it.
- Failed, deferred or malformed post-refresh evidence prevents original dispatch.
  Existing Play Mode deferred and flag-only classifications remain separate.
- The shared command module avoids a state/gate/context import cycle. Some next
  commands inspect state or logs; they do not promise to repair source, licenses
  or a missing executable automatically. Legacy manual Safe Mode guidance remains
  explicitly manual. Coverage of incident actions is not proof about every other or dynamic token.
- Setup reports `unity_editor_bridge_attachment_pending` and an explanatory
  message. It does not emit the proposed categorical `restart_required` field:
  import/domain reload may attach the bridge without restarting the editor.
- Documentation updates cover diagnostics age, recovery, command discovery,
  supported automation, current artifact evidence and the live regression sequence.

## Validation Evidence

- Host suite: `python3 -m unittest discover -s tests` — **1093 tests, OK,
  14 skipped**, on macOS with loopback available and the normal stderr contract.
- Focused recovery, timestamp and setup suite: **89 tests passed**. New lifecycle tests retain
  production registry, gate, state files, journal and lock semantics; only the
  external editor transport and OS process enumeration are substituted.
- Mutation check in an isolated source copy: disabling source-mtime freshness
  made the intended freshness test fail; its two companion controls passed.
- Unity `6000.0.58f2`, documented temporary `no-ugui` package CI fixture:
  **121 EditMode tests passed**, including five new real-file journal cases for
  error text/fallback, no-match, failed and passed verdicts. Core and Test Framework
  assemblies compiled. This is real Unity evidence, not Python source inspection.
- Live MCP recovery in the disposable project: a real fresh compiler error
  refused before submission; fixing the file without manual refresh made the next
  test request perform one refresh, cross a domain reload and pass one test.
  The live .NET round-trip timestamp exposed a seconds-only host parser; the
  shared UTC parser now accepts fractional seconds and a regression checks edits
  on both sides of capture within the same second.
- The uGUI fixture also caught a new global-health regression: labeling an optional
  unregistered capability `degraded` blocked unrelated idle waits. The final status
  is `disabled_unregistered` (or `disabled_dependency_unknown` when unreadable),
  keeping the optional failure local. The first Unity compile found an out-of-scope variable introduced during this
  change; it was corrected before the successful run. The first host run used a
  restricted socket sandbox and a stderr-suppressing setting; neither was treated
  as product proof. The final full run used the normal supported environment.
- Version consistency, release-document freshness, public-safety and diff
  whitespace checks pass. No version bump, release, publication or consumer
  project migration is part of this change.

### Remaining Proof Boundaries

The EditMode run does not establish end-to-end Play Mode reload recovery,
batch-to-GUI build fallback, Windows/Linux process behavior or every supported
Unity version. The declared-but-unregistered uGUI branch was reproduced in a separate live
fixture with only its optional MCP assembly disabled: the original probe reported
missing dependency and the corrected probe reports declared-but-unregistered.
This does not establish that the later healthy snapshot in the archive reproduced
the original pilot state.
The ordered live checks are in `docs/operations/SMOKE_TESTS.md` under
“Diagnostics Freshness and Recovery Regression”. Published-site network checking
was unavailable; these changes do not claim a published site deployment.

## Self-Review and Follow-Up

The fixes use existing policy and transport owners instead of adding another
recovery subsystem. Fresh-error refusal and clean dispatch controls accompany
stale recovery. Refusal events do not inflate the submitted-request denominator.
Error text and test verdict are independently asserted from persisted C# events.
The existing terminal-delivery test now exercises the actual compile gate instead
of a truthy mock that accidentally requested recursive recovery.

What worked: paired controls, the bounded lock test and real Unity compilation
caught integration mistakes that a source-only review would miss. Risks are the
cross-language state contract and editor lifecycle timing; additive fields and
explicitly bounded proof avoid claiming those are universally validated. Preserve
the live smoke sequence for the next package release and record any broader
platform/lifecycle evidence separately.


## Archive Cross-Check and Adequacy Review

The provided archive was inventoried and hashed (339 files). Its 303 primary
journal events contain 24 unique submitted requests, 24 completions and 24 delivery
observations: 14 refreshes, seven Play Mode test runs, one EditMode run, one build
and one Play Mode state change. All five abandoned test requests have later
terminal completion; preserve that recovery behavior.

Raw wrapper output confirms an undated diagnostic labeled `confirmed`, an idle
timeout with a 1522.871-second-old heartbeat despite a live PID, and the mismatch
between transport `ok` and a zero-match test verdict. A completion event has an
empty error reason. Sanitized projections of these boundaries are checked into
`tests/fixtures/retro_recovery_cases.json`; they do not pretend to preserve source
file mtimes or absent historical snapshots.

The bundle's latest state/capability files are later healthy snapshots, not the
frozen/disabled state described by its README. The timeout wrapper references a
different generation from the crash narrative; do not merge those observations.
The editor log does prove a native crash in Android build prerequisites reached
through `ProcessInitializeOnLoadAttributes` and an inline build. It does not prove
which component caused the native fault or why an artifact later disappeared.

Baseline-vs-current executable output separately reproduces missing help verbs
and readiness recommending itself. Source review and paired tests establish the
first-install attachment explanation and missing/empty catalog guidance gaps.
Those are not claims that the archive preserves the original setup/help/catalog
outputs: it does not. The current setup plan in the archive already has the
package dependency. No blanket restart requirement or generic repair mapping is
inferred from it. Detailed private evidence IDs and hashes remain in the private
verification report; no consumer logs or identities were promoted here.
