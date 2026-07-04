# Token-Efficiency Retro: Response Envelope Minimalism

Date: `2026-06-02`
Status: `partially implemented — public token-efficiency backlog`
Source prompt: `docs/archive/retros/CHAT_RETRO_PROMPT.md`
Scope: reusable MCP-surface improvements (public-safe; consumer-project specifics redacted)

## Resolution Update

Partially implemented after this retro:

- `unity_scenario_run_and_wait` returns a compact decision verdict by default,
  with full raw scenario payloads behind `verbose` / `includeFullPayload`.
- MCP tool responses for `unity_project_refresh`,
  `unity_compile_player_scripts`, `unity_compile_matrix`,
  `unity_compile_build_config_matrix`, `unity_tests_run_editmode`, and
  `unity_tests_run_playmode` now default to compact operation summaries that
  keep authoritative post-settle verdict fields while omitting full
  `_xuunity_lifecycle` snapshots unless `includeFullPayload=true`.
- `unity_status_summary` now defaults to a compact MCP polling summary and
  keeps nested discovery, transport, state-group, timing, and artifact details
  behind `includeFullPayload=true`.
- Batch helper CLI commands now accept `--output compact|full`. The default
  remains `full` for compatibility, while compact mode emits the batch decision
  summary and artifact pointers without the full command vector or nested batch
  payload.

Remaining backlog: add compact ceilings for multi-project summaries, add a
token ledger, and define fast-path profiles.

## 1. Executive summary

The session was operationally clean: bridge healthy, no churn, no false negatives,
a code fix validated by one Android player-scripts compile (`passed`, 0 errors,
70 assemblies). **Stability and time-to-diagnosis were not the problem — token
efficiency of the default operator path was.** The MCP surface is heavily
over-serialized: the decision-relevant payload is tiny, but every response wraps
it in a multi-thousand-token envelope of lifecycle snapshots, absolute paths, and
diagnostic groups.

The key finding came from directly measuring the tool advertised as the cheap
path: `unity_status_summary` (described as "compact… low-token diagnostics")
returned **more** JSON than the full `unity_status`. The cost is entirely in
*what is returned to the model*, not in what Unity computes.

## 2. Evidence base (measured)

| Artifact | Real size | Note |
|---|---|---|
| Persisted journal event (`*_request_completed.json`) | 782–798 bytes | Underlying data is tiny |
| `bridge_state.json` | 3.5 KB | Full bridge truth fits in 3.5 KB |
| `unity_status` response | ~5–6 KB JSON | Decision-useful fields: ~10 |
| `unity_compile_player_scripts` response | ~12–13 KB JSON | Decision-useful fields: 5 |
| `unity_status_summary` response | ~5.5+ KB JSON — **larger than full status** | Description claims "compact / low-token" |

Smoking gun: the on-disk truth (`bridge_state.json`) is 3.5 KB, but the `status`
*response about it* is larger, and the "summary" response is larger still.
Serialization, not data collection, is the cost.

Compile response decision surface = `result.{status, error_count, errors[],
compiled_assembly_count, duration_seconds}`. Everything else
(`_xuunity_lifecycle.idle_wait_before`, `idle_wait_after`, `artifact_manifest`,
`structured_timing`, `transport`, `activation`) is envelope.

## 3. Timeline

status check → broad tool-schema search (18 schemas loaded, 2 used) → Android
compile (12 KB response) → done. No retries, no churn, no recovery needed. One
redundant `unity_status` call (compile already returns settle state).

## 4. What worked well

- **Compile-first discipline** — one targeted player-scripts compile confirmed
  the fix; no play mode or test runs needed. Cheapest sufficient validation.
- **Journaling and bridge_state are genuinely lean** (sub-KB / 3.5 KB). The
  backend's own persistence is the model the response envelope should follow.
- **Stability and diagnosis were never in doubt** — health/transport signals
  were unambiguous and time-to-diagnosis was a single operation.

## 5. What worked poorly (token-wise)

1. `unity_status_summary` is mislabeled — it returns `state_groups`,
   `host_prerequisites`, `transport_state`, `bridge_stabilization`,
   `host_health_*`, and a full `artifact_manifest`, i.e. *more* than
   `unity_status`. The genuinely compact nugget (`state_summary` one-liner) is
   buried inside the bloat. Agent workflow docs recommend it for polling —
   currently counterproductive.
2. `compile` embeds two full status snapshots (`_xuunity_lifecycle.idle_wait_before`
   + `idle_wait_after`), ~60 fields each, mostly empty strings — dwarfing the
   5-field `result`.
3. `artifact_manifest` repeats long absolute paths in every response (~6× the
   project root per call). The model never reads these inline.
4. No verbosity control on any tool — full envelope is paid even for a yes/no
   readiness check.

## 6. What was not explicit enough

The contract never states **"collected ≠ returned."** Every diagnostic the
backend gathers is serialized to the model by default, with no tier between a
deep-debug dump and "I just need pass/fail."

## 7. What the operator needed but did not have

A **decision-grade compact response**: for compile → `{status, error_count,
errors[]}`; for status → `state_summary` string + ~12 flags. Both exist as data;
neither is retrievable without the full envelope.

## 8. Scoring (1–10)

| Category | Score | Reason |
|---|---|---|
| Unity-side execution stability | 9 | Clean compile, healthy bridge |
| Request journaling quality | 8 | Tiny, complete events |
| Bridge health observability | 9 | Arguably over-observable |
| Wrapper-to-operator clarity | 6 | Signal buried in envelope |
| Transport lifecycle transparency | 9 | Fully transparent |
| Token efficiency of default path | 3 | The core failure |
| Time-to-diagnosis | 9 | One compile confirmed fix |
| Validation workflow discipline | 8 | Compile-first, nothing heavier |

## 9. Priority improvements (none reduce data collected → stability/quality untouched)

1. **Add `verbosity: compact | default | full`** to `status`, `status_summary`,
   `compile`, `scenario`, `tests`. `full` = today's payload (deep-debug
   preserved). `compact` = decision nugget. Same data collected; less serialized.
   This single change fixes everything below at once.
2. **`compile` default**: return only `{status, error_count, errors[],
   compiled_assembly_count, duration_seconds}`. Move
   `_xuunity_lifecycle.idle_wait_before/after` full snapshots behind
   `verbosity=full`; replace with `idle_before/after: "idle" | "busy:<reason>"`.
3. **Make `unity_status_summary` actually compact** (match its own description):
   `state_summary` string + ~12 decision flags + `errors`. Move `state_groups`,
   `host_prerequisites`, `transport_state` behind `verbosity=full`.
4. **Strip `artifact_manifest` from default responses**: emit `artifact_count`
   plus one `artifact_dir`; full path list only at `verbosity=full`.
5. **Token-budget acceptance check** in smoke contract: each default-verbosity
   response must stay under a byte ceiling (e.g. status ≤ 1.5 KB, compile ≤ 1 KB);
   growth = regression.

## 10. Public-promotion recommendations

- `docs/agents/AGENT_WORKFLOWS.md` — correct the polling guidance: until
  `status_summary` is slimmed, it is not the low-token path. Document the
  verbosity tiers and "compile-as-status" (compile already returns settle state,
  so a separate status call is redundant after a compile).
- `docs/architecture/DESIGN.md` / `docs/architecture/ROADMAP.md` — add the
  principle **"response envelope minimalism: collected ≠ returned."** The backend
  may gather everything; the default response returns only the decision surface.
- `docs/operations/SMOKE_TESTS.md` — add the per-response byte-budget acceptance
  check (item 5) so envelope bloat is caught as a regression.

## 11. Final verdict

Stability: pass. Quality: pass. Token efficiency: fail — and the fix is purely
serialization-side, so it carries zero stability/quality risk. A single
`verbosity` parameter defaulting to `compact`, plus dropping the embedded dual
status snapshots and absolute-path manifests from non-`full` responses, would cut
the default operator path by an estimated **70–85%** (compile ~13 KB → ~1 KB;
status ~5.5 KB → ~1 KB) without removing a single byte of what the backend
collects for deep debugging.

## Operator-side addendum (complementary)

Independent of the MCP surface, recurring operator-side waste worth a standing
habit:

- read large source files by line range when the relevant region is known, not
  whole-file, when only a constructor / single method matters;
- select tool schemas by exact name rather than broad keyword search that loads
  many unused schemas;
- skip a separate status call when a compile/scenario/test response already
  carries settle state.

These pair with the tool-side fixes above and reduce total session cost without
affecting validation rigor.
