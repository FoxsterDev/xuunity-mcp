# Token Accounting And Fast-Path Retro

Date: `2026-06-11`
Status: `public promotion candidate`
Source prompt: `docs/archive/retros/CHAT_RETRO_PROMPT.md`
Scope: reusable MCP/operator improvements; consumer-project details redacted

## 1. Executive Summary

A multi-project MCP package bump completed successfully: every consumer project
was updated, host helper metadata was refreshed, and portfolio compile validation
passed. The operator pain was not correctness. The pain was that the session used
far more model context than the work intrinsically required, and neither the
agent nor the MCP surface could produce a trustworthy token-cost ledger at
closeout.

The token issue had two layers:

- the operator path loaded broad routing, project memory, historical search
  results, and verbose MCP payloads before the task shape required them;
- the toolchain exposed bytes, logs, and JSON, but not a first-class
  per-operation token budget or final token-cost report.

The reusable lesson is that MCP needs both a **fast-path execution profile** and
a **token accounting surface**. Compact response envelopes reduce waste, but the
operator also needs a ledger that says where tokens went.

The governing principle is quality first: maximize task quality, validation
trust, and operator value, then minimize tokens inside that quality envelope.
Token savings are not acceptable if they weaken release, lock, helper,
validation, or failure-investigation evidence.

## 2. Evidence Base

This retro uses a sanitized session timeline rather than raw project evidence.
The relevant observed facts:

- the request was a portfolio-wide version bump plus host helper refresh and
  parallel compile validation;
- the task had a narrow decision surface: target version, project manifests,
  package locks, helper metadata, and compile results;
- the session still loaded broad repo routing, internal routing, validation
  doctrine, project routers, project memory search output, wrapper help, remote
  tag evidence, diff checks, server metadata checks, and full MCP JSON payloads;
- one compile-matrix response returned a large lifecycle envelope when the
  decision surface was effectively `status=passed`, `total=6`, `failed=0`;
- token usage could only be estimated after the fact from transcript shape, not
  measured from a durable counter.

## 3. Timeline

1. Load repo-level routing and public/internal xuunity validation rules.
2. Discover Unity projects and current MCP dependency pins.
3. Inspect project routers and project memory for validation constraints.
4. Confirm the target release tag exists.
5. Switch projects to the target package version and normalize the canonical Git
   UPM URL.
6. Refresh installed host helper/server metadata.
7. Run multi-project compile validation with parallel workers.
8. Reconcile one lock-file edge case, refresh the project, and rerun the narrow
   compile gate.
9. Perform final manifest, lock, helper metadata, and git-status checks.

The execution was disciplined enough to finish correctly, but steps 1, 3, and
parts of 7-9 returned much more text than the operator needed.

## 4. What Worked Well

- **Correctness-first validation** held: the final state was verified through
  manifest/lock checks and MCP compile evidence.
- **Parallel validation** matched the operator request and kept wall-clock time
  under control.
- **Wrapper summaries existed** for multi-project compile and were much cheaper
  than reading every raw Unity log.
- **Manual final reconciliation** caught a lock-file mismatch before closeout.

## 5. What Worked Poorly: Token Spend

The approximate token-cost drivers, in descending order:

| Cost Area | Why It Was Expensive | Future Shape |
|---|---|---|
| Broad routing and doctrine reads | Multiple large prompt files were loaded for a package-only bump. | Use a named MCP package-bump fast path that loads only repo router, MCP mode rule, and validation-lane rule. |
| Wide searches | `rg` over docs/reports/history returned many irrelevant historical MCP hits. | Search only manifests, locks, package metadata, wrapper scripts, and registry docs unless failure forces expansion. |
| Project memory sweep | Project memory output was large and mostly unrelated to dependency bump mechanics. | Skip project memory by default for package-only portfolio bumps unless project router declares a specific validation override. |
| Verbose MCP JSON | Compile and refresh responses included full lifecycle, artifact, and path envelopes. | Default to compact operation results; make full envelope opt-in. |
| Repeated verification commands | Useful checks were split across many commands with repeated file/path output. | Provide one verifier that returns a compact table plus machine-readable artifact. |
| Final JSON payload inspection | Full bridge payload was surfaced to the model when a short result line was enough. | Return `status`, `counts`, `lane`, `request_id`, and `artifact_dir` by default. |

Estimated avoidable token share: roughly **40-60%** for this task class. The
work should fit a `fast path` profile unless validation fails or a project-local
rule forces deeper context.

## 6. What Was Not Explicit Enough

The system has validation lanes and compact summaries, but it does not have an
operator-level policy that says:

- "For package-only portfolio bumps, do not load project memory unless a project
  router explicitly narrows validation";
- "Do not inspect historical reports unless the current command fails";
- "Prefer one structured verifier over repeated shell probes";
- "The final answer must include a token-cost summary when the session was
  expensive."

The lack of an explicit token budget contract let a correctness-oriented agent
choose broader context than the task needed.

## 7. What The Operator Needed But Did Not Have

The operator needed two missing surfaces:

1. **A token ledger**: approximate input/output/tool-result token counts by phase
   and by tool call, including "largest contributors".
2. **A fast-path guardrail**: a mode that constrains the default evidence set for
   known routine tasks and requires escalation only after a failed check or a
   declared risk trigger.

Without these, the closeout can only say "probably expensive" instead of "this
phase used 43% of tokens; this tool output used 18%; compact mode would have
saved 12k tokens."

The operator also needed an explicit quality invariant: token savings must come
from reducing irrelevant context and verbose envelopes, not from removing
release-tag checks, lock verification, helper metadata refresh, compile
evidence, or failure investigation. The target is maximum quality and return on
work with the minimum token volume that still preserves top-level confidence.

## 8. Scoring

| Category | Score | Reason |
|---|---:|---|
| Unity-side execution stability | 9 | Validation completed and final state was reconciled. |
| Request journaling quality | 8 | Sufficient evidence existed, but it was too verbose by default. |
| Bridge health observability | 9 | Healthy; not the bottleneck. |
| Wrapper-to-operator clarity | 7 | Multi-project summary was good; individual payloads were noisy. |
| Recovery guidance quality | 8 | Refresh-plus-compile recovery was clear enough. |
| Transport lifecycle transparency | 9 | More than enough lifecycle detail was available. |
| End-to-end trustworthiness during churn | 8 | Final checks caught and fixed a lock mismatch. |
| Parallel request handling | 8 | Parallelism worked as requested. |
| Token efficiency of default operator path | 4 | Correct but too broad. |
| Token-cost observability | 2 | No first-class measurement, only estimates. |
| Time-to-diagnosis | 7 | Good wall-clock, avoidable context churn. |
| Validation workflow discipline | 8 | Strong validation; could be leaner. |

## 9. Priority Improvements

### P0: Token Accounting Ledger

Add a session-local token ledger that can be reported at closeout:

- per message: approximate tokens in/out;
- per tool call: command name, stdout/stderr bytes, estimated tokens returned to
  the model, truncation status;
- per phase: routing, discovery, mutation, validation, final verification,
  final answer;
- top N largest token contributors;
- estimated savings if compact responses had been used.

This can start as an approximate tokenizer-backed utility. Exact billing-grade
precision is not required for operator learning; stable estimates are enough.

Acceptance criteria:

- every tool call records stdout bytes, stderr bytes, truncation state, and an
  estimated token count returned to the model;
- every agent phase can be tagged as `routing`, `discovery`, `mutation`,
  `validation`, `verification`, or `closeout`;
- the final report can print total estimated tokens, top 5 tool outputs by
  token cost, and top 3 avoidable cost categories;
- the ledger can be emitted without exposing secrets or raw log bodies.

Minimum closeout schema:

```json
{
  "token_report": {
    "profile": "mcp-package-bump-fast",
    "estimated_total_tokens": 0,
    "tool_output_tokens": 0,
    "assistant_output_tokens": 0,
    "largest_outputs": [
      {
        "phase": "validation",
        "tool": "batch-build-config-compile-matrix",
        "estimated_tokens": 0,
        "bytes": 0,
        "truncated": false
      }
    ],
    "avoidable_costs": [
      "project memory loaded without escalation reason"
    ],
    "budget_exceeded": false
  }
}
```

### P0: Compact MCP Response Mode

Add `--output compact|default|full` or `--verbosity compact|default|full` to
wrapper/server commands, especially:

- `request-project-refresh`;
- `request-compile`;
- `request-build-config-compile-matrix`;
- `batch-compile`;
- `batch-build-config-compile-matrix`;
- multi-project runners.

Compact output should contain only:

```json
{
  "operation": "unity.compile.matrix",
  "status": "passed",
  "total": 6,
  "passed": 6,
  "failed": 0,
  "lane": "interactive_mcp",
  "request_id": "...",
  "artifact_dir": "..."
}
```

Full lifecycle, bridge snapshots, artifact path lists, and journal groups should
remain available behind `full`.

Acceptance criteria:

- successful compact compile/matrix responses stay under 1 KB when no errors
  are present;
- successful compact multi-project summaries stay under 500 bytes per project;
- full artifact paths and lifecycle snapshots are omitted from compact output;
- compact output includes one artifact directory or result file pointer for
  follow-up, not every generated path;
- failure output includes enough first-error detail to act without opening raw
  logs immediately.

### P1: Fast-Path Profiles

Introduce named operator profiles:

- `mcp-package-bump-fast`: repo router, MCP version target, manifest/lock
  verifier, helper refresh, compile validation, no project memory by default;
- `mcp-validation-debug`: full routing, project memory, request journal, bridge
  state, raw logs;
- `mcp-release-audit`: broader project memory and generated artifact inspection.

The profile should be printed at start and included in the final report.

`mcp-package-bump-fast` acceptance contract:

- project memory reads: `0` unless an escalation reason is logged;
- historical report searches: `0` unless validation fails;
- raw Unity log reads: `0` for projects with compact passing summaries;
- release tag, manifest, lock, lock hash, helper metadata, and compile evidence
  remain mandatory;
- any ambiguous compact summary escalates to full evidence for that project;
- final closeout: package status, helper status, validation totals, token note;
- any budget breach is explicitly listed in the token note.

### P1: One-Shot Portfolio Verifier

Add a command such as:

```text
xuunity-mcp verify-package-pin --repo-root <root> --package com.xuunity.light-mcp --version 0.3.28 --compact
```

It should return one compact table:

- project;
- manifest pin;
- lock pin;
- lock hash;
- source;
- ok/fail reason.

This replaces multiple ad hoc Python and diff commands.

Verifier exit codes:

- `0`: all project pins and helper metadata match;
- `1`: at least one project mismatch;
- `2`: manifest or lock is unreadable;
- `3`: target release hash cannot be resolved;
- `4`: invalid arguments.

Verifier side effects:

- default mode is read-only;
- mutation mode must require an explicit flag such as `--write`;
- JSON output must be stable enough for CI and final closeout parsing.

### P1: Token Budget Hints In Runner Output

Multi-project runners should emit:

- `summary_only=true`;
- result artifact path;
- number of project summaries;
- omitted raw output byte count;
- suggested next command for failures only.

The operator should not pay tokens for successful project internals.

### P2: Prompt-Stack Dry Run

Add a lightweight prompt-stack selector that reports:

- files it would load;
- estimated token cost;
- reason each file is needed;
- skipped optional layers.

For routine tasks, the operator can accept the fast stack or request full stack.

## 10. Public-Promotion Recommendations

- `docs/agents/AGENT_WORKFLOWS.md`: document the package-bump fast path and the
  rule to skip project memory/historical reports unless validation fails.
- `docs/architecture/DESIGN.md`: add "token accounting is part of operator
  observability" alongside request journaling and bridge state.
- `docs/architecture/ROADMAP.md`: add token ledger, compact response mode, and
  prompt-stack dry run as operator-experience milestones.
- `docs/operations/SMOKE_TESTS.md`: add acceptance checks for compact output
  size and final token-cost reporting.
- MCP wrapper/server templates: implement compact output and a per-command
  `token_estimate` or `output_bytes` field in JSON summaries.

## 12. Concrete Weaknesses Fixed In This Retro

The first draft identified the right problem but was too advisory. This revision
adds:

- measurable acceptance criteria for token ledger and compact output;
- a fast-path budget contract with explicit default-zero reads for memory,
  historical reports, and raw logs;
- implementable verifier and package-bump schemas, including exit codes and
  side-effect rules.
- explicit quality guardrails so token savings cannot be achieved by weakening
  release, lock, helper, validation, or failure-investigation evidence.

## 11. Final Verdict

Validation quality: pass. Operator token efficiency: needs work. Token-cost
observability: missing.

The next reusable improvement should not be another doc-only reminder. It should
be a tool-supported loop:

1. choose a fast-path profile;
2. run compact MCP commands;
3. emit a final token ledger with largest cost centers and estimated savings.

That would let operators tune behavior with evidence instead of guessing after a
large session.
