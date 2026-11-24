# XUUnity Light Unity MCP Chat Retro — SDK rollout: the typed lane was not named, and a file-only check opened an editor

Date: `2026-11-19`
Status: `partial (v0.3.91): RG-54, RG-55, RG-56, RG-57 and RG-59 done; RG-58 and the EDM4U compact payload open`
Lane: one interactive operator chat on `v0.3.90`, Unity `6000.0.58f2` on macOS. A hub project with an open GUI editor plus one closed consumer project. Work: an analytics field fix with new EditMode tests, then an ad mediation adapter bump across sixteen consumer projects (package manifest, lock file and the Android coordinates in `mainTemplate.gradle` and `AndroidResolverDependencies.xml`), then patch-version corrections.

Public twin of a host-private retro. Project names, ticket ids, request ids and local paths are left out.

## Status (2026-11-24, v0.3.91)

| Item | Status | What shipped | What remains / next step |
| --- | --- | --- | --- |
| RG-54 `unity_edm4u_resolve` names no follow-up tool | done (v0.3.91) | `8003a2c`: an Android resolve result lists `unity_sdk_generated_diff_guard` and `unity_sdk_android_resolve` in `next_tools`, with `projectRoot` and the tracked generated paths filled from the files present; `recommended_next_tool` names the guard; the tool description points at the typed lane for rollout proof. | — |
| RG-55 generated diff guard and dropped template lines | done (v0.3.91) | `a96d746`: reproduced first. An allowlisted `*Template.gradle` / `*Template.properties` that lost baseline `**PLACEHOLDER**` tokens or `namespace` / `ndkPath` / `ndkVersion` now fails with `template_markers_dropped`, without caller `requiredMarkersAfter`. | — |
| RG-56 `unity_sdk_dependency_verify` opened an editor for a file read | done (v0.3.91) | `03130ca`: every expectation kind runs on the host as a file read; the editor can be closed, open or busy; `editor_required: false`. | — |
| RG-57 empty `actual_version` on a passing check | done (v0.3.91) | `03130ca`: coordinates are parsed, the found version is returned, and a different version fails instead of passing as a substring. | — |
| RG-58 persisted test result has no executed-test list | open | — | A bounded executed-test list for filtered runs, or per-fixture counts, so one run proves that new tests ran. See also the PlayMode extension in `2026-11-19_ui_driving_and_incomplete_fix_followup_chat_retro.md`. |
| RG-59 dependency verify returns ~10 KB by default | done (v0.3.91) | `03130ca`: the host-side result is small (2.3 KB measured on real files, no editor). | — |
| `unity_edm4u_resolve` default payload size | open | — | It still returns the full `idle_wait_before` / `idle_wait_after` blocks (~14 KB) without `includeFullPayload`. Compact default like refresh, compile and tests. |

## 1. Executive summary

No Unity-side failure and no transport loss: 12 MCP requests, all completed with true verdicts.

The risk in this chat was a silent change to a Unity Gradle template that the MCP saw coming but did not name.

- The operator used the untyped `unity_edm4u_resolve` for the rollout. It honestly returned
  `resolver_output_freshness: unproven`, `decision_ready: false` and
  `recommended_next_action: verify_resolver_output_freshness_and_generated_diff`, but that token named no tool.
- A manual diff showed that the force resolve had also removed `namespace`, `ndkPath` and `ndkVersion` from
  `mainTemplate.gradle` and rewritten the XML header of `AndroidResolverDependencies.xml`. The operator reverted both
  and applied only the adapter lines.
- The typed lanes built for exactly this, `unity_sdk_android_resolve` and `unity_sdk_generated_diff_guard`
  (`SMOKE_TESTS.md` §2a), were never surfaced at the point of use (RG-54). Whether the guard would have flagged lines
  dropped inside a file that is expected to change was unverified (RG-55).

A file-only check launched a Unity editor. `unity_sdk_dependency_verify` on a closed consumer project opened the editor
(17 s, `-accept-apiupdate`) through the generic activation path to read two text files, left it running, and returned a
full lifecycle payload. Over sixteen projects that is sixteen editor launches for a grep (RG-56). Its passing results
carried `actual_version: ""` (RG-57).

Smaller gaps: proving that 4 new tests ran took a second group-filtered run and a count comparison, 9 → 13 (RG-58);
`unity_edm4u_resolve` and `unity_sdk_dependency_verify` returned ~10–14 KB non-compact payloads by default (RG-59 and
the EDM4U payload row).

## 2. Findings

| Finding | Severity | Attribution | Basis |
| --- | --- | --- | --- |
| RG-54 The EDM4U success payload points to "verify" in prose only | P1 discoverability | `unity_edm4u_resolve` result model | The next action is a string token, not a tool with arguments. The obvious tool by name is the untyped one, and the typed lanes live only in `SMOKE_TESTS.md` §2a. |
| RG-55 Unknown whether the guard catches dropped template lines in an expected-changed file | P2 verification | `unity_sdk_generated_diff_guard` | A template on `expectedChangedAllowlist` passed unless the caller supplied `requiredMarkersAfter`. Reproduced before the fix. |
| RG-56 A read-only dependency check opens an editor | P1 side effect | `unity_sdk_dependency_verify` activation | Every expectation kind is a file read, yet the call took the bridge activation path, cold-started the editor and left it running. |
| RG-57 `actual_version` empty on pass | P2 evidence | `android_resolver_package` / `gradle_dependency` expectations | The check matched the expected value as a substring and never reported the version it found. |
| RG-58 No executed-test list in the persisted result | P2 evidence | persisted test result | The result has counts and the last started and finished test only, so "the new tests ran" needs a second, narrower run. |
| RG-59 Non-compact default payload | P3 token cost | `unity_sdk_dependency_verify` | About 10 KB of lifecycle and launch fields on a passing check. |

## 3. Timeline

1. `unity_status_summary` reported `editor_domain_currency: stale` with the exact six changed inputs and
   `run_unity_project_refresh_before_invoking`. The refresh that followed confirmed the compile.
2. EditMode for the touched area passed, then an iOS compile. The persisted result could not show that the new tests
   were among the passing ones, so the fixture group ran again: 13/13, 9 before the change.
3. Manifest and lock edits in sixteen projects, then refresh and package resolve in the hub project. Target versions
   were read from `Library/PackageCache/*/package.json` by hand, not from MCP.
4. `unity_edm4u_resolve`: honest `unproven`; the manual diff found the template damage; reverted.
5. Android and iOS compiles green. The new Android coordinates were checked upstream by hand; there is no MCP lane for
   "this coordinate exists in the repository".
6. Patch corrections: refresh and resolve again, versions confirmed from the package cache again.
7. `unity_sdk_dependency_verify` on the closed consumer project opened its editor. The CLI quit was then blocked by the
   agent harness, so the editor stayed open.

## 4. What worked well

- `unity_status_summary` named the stale editor domain with the exact changed inputs and the right next action.
- Refresh reported `post_settle_compile: passed / confirmed` after every edit; no false greens.
- `rebuilt_assembly_count` against `cached_assembly_count` showed that the second iOS compile proved nothing new, since
  the adapter packages carry no C#.
- `unity_edm4u_resolve` refused to claim freshness, and that `unproven` flag is what triggered the manual diff.
- Test runs had clean accounting, complete console-error accounting since request start, and compact payloads.

## 5. What the operator needed but did not have

- A next-tools hint with prefilled arguments after `unity_edm4u_resolve` (shipped as RG-54).
- An editor-free dependency verify for closed projects across a portfolio (shipped as RG-56).
- Executed test names, or per-fixture counts, in a filtered test result (RG-58, open).
- Resolved package versions in the refresh-and-resolve payload; they were read from the package cache twice.

## 6. Scoring (1–5)

| Category | Score | Note |
| --- | --- | --- |
| Unity-side execution stability | 5 | 12/12 completed, true verdicts |
| Request journaling quality | 4 | complete; the test result lacks executed names |
| Bridge health observability | 5 | stale-domain detection exact |
| Wrapper-to-operator clarity | 3 | prose next action without a tool; the verify side effect undisclosed |
| Recovery guidance quality | 3 | correct direction, no concrete tool |
| Transport lifecycle transparency | 4 | the cold start was fully reported, after the fact |
| End-to-end trustworthiness during churn | 4 | no false greens; template damage caught by the operator, not the MCP |
| Parallel request handling | n/a | sequential |
| Token efficiency of the default operator path | 3 | compact for refresh, compile and tests; ~10–14 KB for EDM4U and verify |
| Time-to-diagnosis | 4 | damage found in one diff |
| Validation workflow discipline | 3 | the operator skipped the documented typed lane |

## 7. Evidence

- The request journal of the hub project: eleven completed requests (status, refreshes, two EditMode runs, three
  compiles, two package resolves, one EDM4U resolve). The consumer project's journal: one
  `unity.sdk.dependency.verify` with `editor_opened_by_this_call: true`, `editor_open_duration_seconds: 17.007` and
  `cold_start_reason: stale_bridge_and_host_session`.
- The persisted EditMode result (2.6 KB) carries `total`, `passed`, `last_started_test` and `last_finished_test` and
  no executed-test list.
- The git diff of `mainTemplate.gradle` after the EDM4U resolve: the adapter lines, plus removed `namespace`,
  `ndkPath` and `ndkVersion`, plus an XML header rewrite in `AndroidResolverDependencies.xml`.
- After the fix, a read-only check on two real projects' files: `unity_sdk_dependency_verify` answered in 1 ms with a
  2.3 KB payload and no editor, a wrong version failed, and the template guard named the three dropped lines in both
  real `mainTemplate.gradle` files.
- The `## 0.3.91` section of `CHANGELOG.md` is the record of what shipped.

## 8. Final verdict

The MCP was correct throughout and honest about what it had not proven. The weak spot was discoverability: the safe
SDK path existed but was not the one an agent reached for, and the cheap-looking verification tool was not cheap.
`v0.3.91` turns this chat's manual diff and editor launch into typed calls. Why the force resolve dropped those
template lines in that one project is a consumer-side follow-up, not MCP work.

## Related

- `2026-05-14_sdk_rollout_mcp_portfolio_retro.md` introduced the typed resolver, package restore and generated diff
  guard; its orchestration items remain open.
- `2026-11-19_ui_driving_and_incomplete_fix_followup_chat_retro.md` is the other retro of the same release batch
  (RG-60..RG-72) and extends RG-58 to PlayMode results.
