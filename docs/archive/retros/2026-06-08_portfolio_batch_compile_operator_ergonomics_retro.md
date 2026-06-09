# XUUnity Light Unity MCP Portfolio Batch Compile Operator Ergonomics Retro

Date: 2026-06-08
Status: public-safe sanitized, implemented
Source: sanitized from a host-private multi-project batch compile retro

## Executive Summary

The batch compile lane was technically reliable, but the default operator
surface was too verbose for portfolio-scale validation. The wrapper had enough
evidence to prove success, yet the live stream made the operator reconstruct
the verdict manually.

## Public Lessons

- Multi-project batch validation needs compact rows while preserving full JSON
  artifacts.
- Aggregate verdicts should be visible without raw-log inspection.
- Result artifacts are stronger closeout evidence for completed compile proof
  than live bridge state.
- GUI fallback and license/blocker reasons belong in compact rows, not only
  deep JSON.
- Successful loops should emit a final aggregate summary with passed/failed
  counts and compiler error totals.

## Implemented Public MCP Outcomes

- compact batch progress and result summaries.
- aggregate multi-project compile verdicts.
- compact per-project rows with requested/effective lane and transport/Unity
  outcome.
- batch result summary artifacts.
- docs that prefer compact summary-first evidence over raw batch logs.

## Sanitization Notes

Project names, exact portfolio composition, local artifact paths, private
config names, and proprietary validation context were removed. The retained
content is the reusable batch operator pattern.

## Final Verdict

This retro is complete for public MCP history. Private portfolio project sets
and project-specific validation rules remain outside the public archive.
