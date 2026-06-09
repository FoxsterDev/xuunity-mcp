# XUUnity Light Unity MCP Token Stability And Summary-First Recovery Retro

Date: 2026-05-07
Status: public-safe sanitized, implemented
Source: sanitized from a host-private single-project MCP session retro

## Executive Summary

The session exposed two distinct failure classes that should stay separate in
operator output:

- real Unity-side failures, such as compile/test errors or project-lock
  conflicts
- transport/session continuity churn, where Unity may still have completed the
  operation but the wrapper lost a clean response path

The expensive part was not the request journal itself. The expensive part was
repeated polling and repeated fallback to large raw logs when compact recovery
surfaces were not obvious enough.

## Public Lessons

- Prefer summary-first recovery after lifecycle churn.
- Make `request-final-status` the obvious next step when a request loses
  continuity.
- Keep transport outcome and Unity operation outcome separate.
- Treat repeated raw scenario-result polling as a fallback, not the default
  operator loop.
- Failed batch paths need compact failure summaries, just like successful batch
  paths need compact result summaries.
- Healthy-but-busy bridge states need operator wording, not only raw state
  fields.

## Implemented Public MCP Outcomes

- `request-status-summary` and status compact output.
- `request-final-status` recovery flow.
- persisted scenario result summaries.
- batch failure summaries and compact batch result rows.
- compiler diagnostics in status summaries.
- summary-first recovery guidance in public docs and smoke flows.

## Sanitization Notes

Project names, local paths, raw request ids, exact project evidence, and
private business context were removed. Counts and examples were generalized to
the reusable MCP behavior.

## Final Verdict

This retro is complete for public MCP history. The reusable lesson is that
compact recovery surfaces should lead the operator before raw logs, raw
scenario polling, or repeated retries.
