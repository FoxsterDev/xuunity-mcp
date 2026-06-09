# XUUnity Light Unity MCP Project Action Hook Scaffold Retro

Date: 2026-06-08
Status: public-safe sanitized, implemented
Source: sanitized from a host-private project-defined hook authoring retro

## Executive Summary

Project-defined hooks were already a useful execution surface, but authoring a
new hook was too manual. The missing piece was not another ad hoc launcher; it
was a predictable scaffold and activation lane for creating, registering,
refreshing, validating, and safely invoking catalog-backed project actions.

## Public Lessons

- Repeatable Unity operations should live behind a project-defined MCP hook
  when they need Unity/editor context.
- Shell wrappers can launch a flow, but they should not become the source of
  truth for project-specific Unity behavior.
- New hook activation needs an explicit order:
  scaffold, add implementation, merge catalog entry, refresh/compile, list
  actions, validate scenario, run non-mutating smoke, then allow mutation.
- Mutating fan-out hooks should expose non-mutating preflight actions such as
  list-targets or dry-run.
- Project-action diagnostics need to show enough scenario validation detail to
  avoid falling back to raw hook scenarios.

## Implemented Public MCP Outcomes

- typed project action catalog/list/invoke flow.
- project-action normalization before scenario dispatch.
- mutation approval semantics.
- project-defined hook summary promotion in scenario summaries.
- `project-hook-scaffold`, generating:
  hook class template, catalog fragment, activation smoke scenario, and
  activation checklist.
- regression coverage for scaffold output and parser availability.

## Sanitization Notes

Project hook names, project paths, product configuration assets, satellite
project discovery rules, and private launcher details were removed. The
retained content is the reusable hook-authoring workflow.

## Final Verdict

This retro is complete for public MCP history. Concrete project hooks and
project-specific fan-out policy remain host/project backlog.
