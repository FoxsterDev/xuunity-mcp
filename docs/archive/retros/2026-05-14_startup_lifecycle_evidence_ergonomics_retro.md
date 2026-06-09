# XUUnity Light Unity MCP Startup Lifecycle Evidence Ergonomics Retro

Date: 2026-05-14
Status: public-safe sanitized, implemented
Source: sanitized from a host-private startup lifecycle and profile-mutation retro

## Executive Summary

The Unity-side fix in the source session was trustworthy after the editor bridge
became healthy. The MCP lesson was broader: startup and profile-sensitive
validation needs compact, targeted evidence rather than broad console tails,
raw scenario JSON, or project-specific smoke scripts.

## Public Lessons

- Status recovery should distinguish stale/offline bridge state from live
  healthy editor state.
- Scene validation needs pass/fail assertions, not only snapshots.
- Console evidence should support focused grep-style queries with stack traces
  omitted by default.
- Profile/environment mutation scenarios should warn when restore or final
  profile assertion evidence is missing.
- Generic profile-mutation templates should prefer:
  apply profile, wait for compile/status settle, collect focused evidence,
  restore or assert final profile, then compile gate.
- Loading/startup timing probes should use compact matching helpers instead of
  broad console tails.

## Implemented Public MCP Outcomes

- `unity.scene.assert` and scenario `assert_scene`.
- `unity.console.grep`, `unity_console_grep`, CLI `request-console-grep`, and
  scenario `console_grep`.
- `unity_loading_timing` and CLI `request-loading-timing`.
- `profile_mutation_summary` in scenario result summaries.
- generic profile mutation scenario template.
- compact scenario/project-action/console-grep wrapper summaries.
- live Unity smoke coverage for direct console grep, invalid regex handling,
  scenario validation/run without explicit `limit`, and loading-timing helper
  invocation.

## Sanitization Notes

Project names, profile names, scene names, local scenario paths, commit ids,
delivery-channel details, and product-specific startup behavior were removed.
The retained content is only the reusable MCP evidence pattern.

## Final Verdict

This retro is complete for public MCP history. Remaining project-specific smoke
flows stay in host/project backlog and are intentionally not part of this public
archive record.
