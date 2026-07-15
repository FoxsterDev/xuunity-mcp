# EditMode Targeted Filter Zero-Match Contract Retro

Date: `2026-07-15`
Status: `implemented contract hardening; consumer-project Unity verification passed`

## 1. Executive Summary

A direct EditMode request with four fully qualified test names completed with
zero selected tests. Unity did not execute or fail those tests. The persisted
result correctly recorded `total=0` and payload status `no_tests`, but the
transport-level request status was `ok`; that combination is unsafe if an
operator treats the request status as validation success.

After one forced project refresh, the same fully qualified filter selected and
passed its target, and a following full assembly run passed. Therefore the
incident is not a general incompatibility with fully qualified names. It is a
stale discovery/import case compounded by a zero-match result contract that is
too easy to misread as a pass.

## 2. Evidence Base

- Request-journal submitted, started, completed, and delivery-observed events
  proved that every request reached the live bridge.
- The persisted test-result artifact for the first targeted request recorded
  `total=0`, no started test, no finished test, `no_tests`, and no lifecycle
  churn.
- The bridge remained healthy and idle; a forced asset refresh recreated the
  bridge identity without compiler errors.
- A repeated fully qualified single-test request then recorded `total=1` and
  `passed=1`; the final unfiltered assembly run recorded `163/163` passed.
- The current test callback implementation intentionally maps zero selected
  leaves to payload status `no_tests`, while the outer response remains `ok`.

## 3. Timeline

1. A representative player-script compile completed without compiler errors.
2. A direct EditMode request specified four fully qualified test names and an
   assembly. It completed with zero selected tests.
3. A forced project refresh completed, including the expected bridge identity
   change and idle settle.
4. The same fully qualified test-name form selected one test and it passed.
5. A final assembly-wide EditMode run selected and passed all discovered tests.

## 4. What Worked Well

- The request journal and persisted result artifacts were enough to separate
  successful request delivery from successful validation.
- Bridge status exposed an idle, compiler-clean editor after the refresh.
- The compile-first workflow made a code compilation failure unlikely before
  testing began.
- An assembly-wide rerun supplied conclusive validation once discovery was
  refreshed.

## 5. What Worked Poorly

- A requested filter that selected zero tests retained outer request status
  `ok`, creating a false-positive path for callers that read only transport
  status.
- The compact status path did not make `total=0`, the filter summary, and the
  required recovery equally visible.
- The documented refresh recovery for externally changed C# sources does not
  explicitly cover a targeted test request that discovers no tests.
- The reflection-based resolver can have no loaded test assembly to catalogue
  before the Test Runner loads it, so a newly imported test is especially
  vulnerable to this discovery gap.

## 6. What Was Not Explicit Enough

- `no_tests` is not a passing validation result when the caller supplied a
  test, group, category, or assembly filter.
- A caller needs a single recovery sequence: refresh once, retry once, then
  classify the result as a filter mismatch if it is still empty.
- Direct test output needs to surface the test counts and filter summary
  without requiring raw journals or result-file inspection.

## 7. What the Operator Needed but Did Not Have

- A terminal `test_filter_no_match` verdict distinct from an unfiltered project
  that simply contains no tests.
- An explicit compact recovery command such as a project refresh followed by
  the same request.
- A non-success validation/CLI classification for a filtered request with
  `total=0`, while still preserving that transport and Unity callback delivery
  succeeded.

## 8. Scoring

| Category | Score | Rationale |
| --- | ---: | --- |
| Unity-side execution stability | 9/10 | Refresh and both subsequent test runs completed normally. |
| Request journaling quality | 9/10 | The lifecycle and final zero-count evidence were durable and decisive. |
| Bridge health observability | 8/10 | Healthy/idle state and identity change were visible. |
| Wrapper-to-operator clarity | 3/10 | Outer `ok` obscured an empty requested selection. |
| Recovery guidance quality | 5/10 | Refresh worked but was not the explicit targeted-test recovery branch. |
| Transport lifecycle transparency | 8/10 | Bridge generation change was observable and recoverable. |
| End-to-end trustworthiness during churn | 6/10 | Artifacts preserved truth, but the default status could mislead. |
| Parallel request handling | 8/10 | Requests were serialized and no request was lost. |
| Token efficiency of the default operator path | 4/10 | Diagnosis required repeated status polling and raw artifact inspection. |
| Time-to-diagnosis | 6/10 | Strong artifacts existed, but their relation to the compact status was not direct. |
| Validation workflow discipline | 8/10 | Compile-first and final full-suite confirmation prevented a false conclusion. |

## 9. Priority Improvements

1. **P1 — classify a requested zero-match as `test_filter_no_match`.** Persist
   whether any filter was supplied. When Unity completes with `total=0` and a
   filter was requested, keep transport delivery separate but emit a
   non-passing validation verdict, the filter summary, and a retry command.
2. **P1 — expose compact direct-test counts.** Every direct test completion
   should place `total`, `passed`, `failed`, `skipped`, test verdict, and
   `filter_summary` in the default wrapper summary.
3. **P1 — add cold-discovery coverage.** Create an integration regression that
   changes or adds a test source, performs the documented refresh, then proves
   a fully qualified targeted request selects exactly the expected leaf.
4. **P2 — strengthen resolver loading.** When an assembly filter is supplied,
   the resolver should attempt to load the requested test assembly before
   cataloguing names, while retaining a safe fallback for assemblies that are
   unavailable during compilation.
5. **P2 — document a one-refresh rule.** On a requested zero-match after
   external C# edits, refresh once and retry once; if it remains empty, stop as
   a filter mismatch rather than retrying indefinitely.

## 10. Public-Promotion Recommendations

- Add the zero-match decision rule to the public smoke contract and direct-test
  wrapper help.
- Add source and wrapper regression tests for filtered zero-match classification
  and compact count propagation.
- Add the recommended recovery command to persisted test payloads and compact
  status summaries.
- Do not auto-refresh repeatedly after every empty filter result: it can be
  costly and hide a genuine spelling/assembly mismatch. One explicit refresh
  retry is the deterministic recovery boundary.

Implementation note: the bridge now persists `filter_requested`,
`filter_summary`, `test_verdict`, and a one-refresh recovery command. Filtered
zero totals become `test_filter_no_match` while outer transport delivery stays
`ok`; the resolver attempts a safe load of a requested assembly before it
catalogues names. Source and wrapper regression coverage guard this contract;
the dedicated live smoke adds a test source, refreshes, and selects its fully
qualified leaf in Unity.

Consumer-project Unity verification completed on `2026-07-15`: the
cold-discovery smoke selected and passed its single fully qualified EditMode
leaf after one refresh, and the package self-test runner passed `16/16`
EditMode tests (including the zero-match classification self-test) plus `5/5`
PlayMode tests. The runs settled compiler-clean and the temporary consumer
manifest testable entry was restored afterward.

## 11. Final Verdict

The first targeted request was neither a passing test nor evidence that fully
qualified filters are unsupported. It was a completed zero-match caused by
stale test discovery. The durable result artifact made that distinction
provable, and the post-refresh targeted and full runs verified the filter form.
The public MCP contract still needs to make a requested zero-match impossible
to misclassify as validation success.
