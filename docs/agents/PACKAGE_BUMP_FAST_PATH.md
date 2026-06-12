# MCP Package Bump Fast Path

Date: `2026-06-11`
Status: `public guidance`

## Purpose

Use this playbook when an agent must update `com.xuunity.light-mcp` across one
or more Unity projects and validate the result without spending unnecessary
tokens on broad project investigation.

This is a package-version workflow, not a gameplay, SDK, or architecture review.
The default path should be lean and evidence-driven.

Top principle: maximize task quality, validation trust, and operator value while
using the minimum token volume that can still support that quality. Token savings
are never allowed to weaken release, lock, helper, validation, or
failure-investigation evidence.

## Use When

- the requested work is a package pin bump, for example `v0.3.27` to `v0.3.28`;
- the expected mutation is limited to `Packages/manifest.json` and
  `Packages/packages-lock.json`;
- host helper/server refresh is part of the same version bump;
- validation is compile/package-resolution health, not runtime behavior.

Do not use this fast path when the request also changes MCP source code,
consumer gameplay code, SDK wrappers, build processors, native plugins, store
metadata, or runtime behavior. Escalate to the normal project workflow instead.

## Agent Contract

MUST:

- load only the repo/project routing needed to confirm MCP package mode and
  allowed validation lanes;
- discover target projects from `Packages/manifest.json`;
- verify the target release tag before mutating project manifests;
- keep the canonical Git UPM URL as `https://github.com/FoxsterDev/xuunity-mcp.git`;
- refresh installed host helpers in the same closeout;
- validate after manifests and locks are in their final form;
- report lane type honestly, including GUI fallback;
- end with a compact manifest/lock/helper/validation summary.

MUST NOT:

- read project memory by default;
- search historical reports or archive folders before a failure;
- inspect raw Unity logs for projects that already have a passing compact
  summary;
- paste full MCP lifecycle JSON into the final answer;
- call `prodmode` or a manifest edit "validated" before package refresh or
  compile evidence exists;
- leave a missing or stale `packages-lock.json` entry unreported.

Escalate when:

- a project router explicitly overrides this fast path;
- the release tag is missing or points at an unexpected package version;
- manifest and lock disagree after refresh;
- validation fails or returns ambiguous/fallback evidence;
- the requested work touches runtime code, SDK/native/build processors, or
  generated build artifacts.

## Token Budget Rule

For routine package bumps, start with the narrowest evidence set:

1. repo/project router rules that directly mention MCP package mode or
   validation lanes;
2. project manifests and package locks;
3. MCP package metadata and release tag evidence;
4. wrapper help only when command shape is uncertain;
5. compact validation summaries.

Skip by default:

- project memory;
- historical reports;
- broad `rg` over docs/archive/report folders;
- raw Unity logs for successful projects;
- full MCP lifecycle JSON when compact summaries prove the result.

Escalate only after a failed check, missing lock, package-resolution failure,
validation failure, or a project-local rule that explicitly overrides this path.

Suggested budget ceilings for one routine portfolio bump:

| Phase | Ceiling | Notes |
|---|---:|---|
| Routing reads | 3 files | Repo router, MCP package/validation rule, optional project override only. |
| Discovery searches | 4 commands | Project manifests, locks, package metadata, release tag. |
| Historical/project memory reads | 0 by default | Any use requires an escalation reason. |
| Successful validation output | 1 compact summary | Raw logs only for failures or inconsistent summaries. |
| Final response | 25 lines | Include token note only as compact bullets. |

If a phase exceeds its ceiling, record why in the closeout token note.

## Quality Guardrails

This fast path reduces token spend only by narrowing context and response
volume. It must not reduce validation quality.

Quality is the priority. The fast path is successful only when it delivers the
same or stronger final confidence as the broader workflow with less irrelevant
context, less duplicated output, and fewer raw logs.

Never cut:

- release-tag verification before mutation;
- manifest and lock agreement checks;
- lock hash comparison against the release commit;
- installed helper/server metadata verification;
- package refresh or compile evidence after the final manifest/lock state;
- failure investigation for any project with a non-passing or ambiguous result;
- explicit reporting of validation gaps.

Allowed cuts:

- skip project memory when the package bump has no project-specific behavior
  surface;
- skip historical reports before a failure;
- prefer compact summaries over full lifecycle JSON for successful operations;
- omit raw Unity logs for projects with trustworthy passing summaries;
- combine repeated shell probes into one structured verifier.

If a compact summary is inconsistent, incomplete, or missing final accounting,
the agent must escalate to full evidence for that project. Token savings are
secondary to a trustworthy validation claim.

## Lean Process

1. Discover target Unity projects by `Packages/manifest.json`, then filter to
   projects that declare `com.xuunity.light-mcp`.
2. Confirm the target release tag exists on the canonical public repo.
3. Update each manifest pin to:

   ```text
   https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v<version>
   ```

4. Update or let Unity regenerate the matching `packages-lock.json` entry.
5. Refresh installed host helpers from the same source checkout.
6. Verify host helper package metadata reports the target version.
7. Run the approved MCP compile validation lane:
   - use multi-project batch validation with explicit `--parallelism` when
     validating a portfolio;
   - use the project-config-aware build-config matrix when available;
   - use interactive MCP only when a live editor blocks batch or project rules
     require it.
8. Run one final verifier over every touched project:
   - manifest pin equals target;
   - lock pin equals target;
   - lock hash equals the release commit;
   - lock source is `git`;
   - no package entry is missing.
9. Close out with only:
   - projects updated;
   - helper/server metadata version;
   - validation totals;
   - validation gaps, if any;
   - unexpected dirty or untracked paths.

## Done When

The fast path is complete only when all of these are true:

- every touched manifest pin equals the requested target version;
- every touched lock entry exists and matches the target version;
- every touched lock entry has `source: git`;
- every touched lock entry hash matches the target release commit;
- installed helper metadata reports the same package version;
- package refresh or compile evidence was produced after the final lock state;
- validation totals are available as a compact summary;
- any GUI fallback, missing lock regeneration, or skipped validation is reported
  as a gap.

## Preferred Command Shape

Use the repo or host wrapper when it exists:

```bash
WRAPPER=AIOutput/Operations/XUUnityLightUnityMcp/xuunity_light_unity_mcp.sh
```

Fall back to the public source wrapper only if the host wrapper is missing:

```bash
WRAPPER=AIRoot/Operations/XUUnityLightUnityMcp/xuunity_light_unity_mcp.sh
```

For published release state, use `prodmode` only after the target tag is visible
on the remote:

```bash
"$WRAPPER" prodmode --project-root "$PROJECT_ROOT"
```

If wrapper output selects a legacy remote URL, normalize the manifest back to
the canonical public package URL shown above before validation.

Refresh installed helpers before closeout:

```bash
bash AIRoot/Operations/XUUnityLightUnityMcp/init_xuunity_light_unity_mcp.sh --target both --force
```

## Validation Rules

- Treat mode switching as mutation only, not validation.
- A successful package bump needs package refresh or compile evidence after the
  manifest and lock are in final form.
- For portfolio validation, prefer the multi-project runner and set the
  requested parallelism explicitly.
- Do not inspect raw logs for successful projects unless the compact summary is
  inconsistent.
- If a project uses GUI fallback because an editor is already open, report that
  lane honestly and run a narrow follow-up compile if the lock changes after the
  first validation pass.

## Compact Closeout Template

```text
Updated:
- <N>/<N> projects pinned to com.xuunity.light-mcp#vX.Y.Z
- manifests and locks agree; release hash <hash>
- host helper metadata reports X.Y.Z

Validation:
- multi-project compile: <N>/<N> passed, parallelism=<N>
- lanes: <batch count> batch, <fallback count> GUI fallback
- extra follow-up gates: <none or project/status>

Token note:
- fast path used; skipped project memory and historical reports
- largest output: <runner summary or failed payload>
```

## Future Tooling Target

This workflow should eventually be backed by one command:

```text
xuunity-mcp package-bump \
  --repo-root <repo> \
  --package com.xuunity.light-mcp \
  --version vX.Y.Z \
  --parallelism 3 \
  --compact
```

The command should produce a compact manifest/lock/helper/validation report and
a token-cost summary for the session.

Minimum result schema:

```json
{
  "status": "passed",
  "package": "com.xuunity.light-mcp",
  "version": "vX.Y.Z",
  "release_hash": "...",
  "projects_total": 10,
  "projects_updated": 10,
  "projects_failed": 0,
  "helper_version": "X.Y.Z",
  "validation": {
    "status": "passed",
    "parallelism": 3,
    "batch_passed": 9,
    "gui_fallback_passed": 1,
    "failed": 0
  },
  "token_report": {
    "profile": "mcp-package-bump-fast",
    "estimated_tokens": 0,
    "largest_output": "",
    "skipped_project_memory": true,
    "skipped_historical_reports": true
  },
  "projects": [
    {
      "name": "ExampleProject",
      "manifest_ok": true,
      "lock_ok": true,
      "lock_hash": "...",
      "validation_status": "passed",
      "lane": "batch"
    }
  ]
}
```

Expected exit codes:

- `0`: all manifests, locks, helper metadata, and validation passed;
- `1`: validation failed for at least one project;
- `2`: mutation or package-resolution failed;
- `3`: release tag or helper metadata mismatch;
- `4`: invalid arguments or unsupported project layout.
