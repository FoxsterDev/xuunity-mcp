# UI PlayMode Smoke Operator Speed Retro

Date: 2026-06-16
Status: public-safe active design retro
Scope: reusable XUUnity Light MCP and Game QA lessons for small, fast UI PlayMode post-validation smokes

## Executive Summary

Small UI runtime validations should take minutes, not a long exploratory loop.
The core bridge primitives are now strong enough for this class of work:
`project_defined_hook_poll_until`, compact scenario summaries, screenshots,
console grep, cleanup, and compile gates exist. The remaining high-value work is
operator ergonomics and proof quality:

- summarize the exact UI user path that was proven;
- prevent a neighboring happy path from satisfying the required bug path;
- classify startup/lobby/popup readiness separately from product assertion
  failures;
- make the default evidence pack compact enough to read before raw JSON.

## What Is Already Solved

- Async project-defined UI flows can use `project_defined_hook_poll_until`
  instead of fixed wait/snapshot ladders.
- Scenario summaries can promote hook terminal status, selected scalar payload
  fields, screenshot paths, console-tail evidence, and cleanup result.
- Package-bump workflows have a lean fast-path playbook and helper metadata
  verification guidance.
- UI-heavy review policy requires automated evidence, an explicit manual recipe,
  or a named capability gap at closeout.
- Optional private Game QA packs can be routed by capability without hardcoding
  private paths into public policy.

## Highest-ROI Remaining Work

P0: UI-smoke semantic verdict profile.

- Add a compact result mode or summary profile that leads with:
  - run id and terminal status;
  - first meaningful failed step;
  - failure class: `product_assertion`, `startup_lobby`, `precondition`,
    `blocking_popup`, `infrastructure`, or `cleanup`;
  - selected path row;
  - selected tab or screen;
  - before/after model value;
  - before/after real UI value;
  - screenshot path;
  - cleanup/PlayMode exit status.

Why this pays off:
one readable verdict avoids raw scenario JSON inspection and prevents agents from
claiming "looks good" from incomplete evidence.

P0: path coverage matrix for UI smokes.

- Let scenarios or hooks declare required path rows, such as primary path,
  fallback path, hidden-tab update path, popup-dismissal path, ad-return path, or
  reward-claim path.
- Require hook payloads to report `user_path` or equivalent.
- Summaries should state which required row passed, failed, or was unavailable.

Why this pays off:
a passing adjacent path is often real evidence but not proof of the regression
path. This is the fastest way to stop false closeout.

P1: startup/lobby/popup readiness classification.

- Split app readiness into named checkpoints:
  - PlayMode entered;
  - startup scene left;
  - lobby or target scene loaded;
  - target root found;
  - target model or backing state found;
  - target view found;
  - blocking popup absent or dismissed.
- Fail early with a named readiness class instead of consuming the full product
  assertion timeout.

Why this pays off:
startup or popup stalls should not be diagnosed as product UI failures, and they
should not burn the whole smoke budget.

P1: cleanup-safe scenario cancellation.

- Expose or document a "cancel body, run cleanup/finally tail" operation for
  scenarios already known to be doomed.

Why this pays off:
operators can stop expensive waits without leaving PlayMode, build profiles, or
local state dirty.

P2: project hook inventory template.

- Standardize optional project hook actions:
  - list user paths;
  - list blocking popups;
  - close current blocking popup;
  - list validation fixtures;
  - snapshot current screen.

Why this pays off:
new projects become faster to map, but the first four items above reduce active
validation time sooner.

## Public Design Direction

The public MCP layer should stay project-neutral. It should provide:

- scenario primitives;
- result summary profiles;
- failure-class vocabulary;
- path coverage matrix conventions;
- cleanup and evidence contracts.

Project code should own:

- product-specific view/model lookup;
- exact user path actions;
- popup taxonomy;
- fixture/profile safety;
- assertions on the real UI state.

## Final Verdict

The reusable investment with the highest return is not more broad automation.
It is a small UI-smoke loop that reads like:

1. discover available hooks/scenarios/click helpers;
2. declare the exact required path row;
3. run one poll-until user-flow hook;
4. capture one compact evidence pack;
5. report a semantic verdict and cleanup status.

That path keeps runtime UI validation trustworthy while making it fast enough to
use after ordinary UI bug fixes.
