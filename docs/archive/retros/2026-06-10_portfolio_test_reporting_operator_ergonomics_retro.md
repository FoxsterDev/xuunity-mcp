# XUUnity Light Unity MCP Portfolio Test Reporting Operator Ergonomics Retro

Date: 2026-06-10
Status: public-safe sanitized, implemented
Source: sanitized from a host-private multi-project manifest update and test run retro

## Executive Summary

A portfolio-scale MCP validation run completed its Unity request lifecycle, but
the operator had to manually reconstruct the portfolio verdict from individual
test result artifacts and workspace status. The reusable issue was not transport
stability; it was missing aggregate reporting for completed test runs.

## Public Lessons

- Completed test result JSON is the source of truth for Unity Test Framework
  outcomes.
- Test result counts are top-level fields: `total`, `passed`, `failed`, and
  `skipped`.
- Portfolio closeout must distinguish MCP operation success from test-suite
  failure.
- Repeated first-failure classes should be grouped across projects so shared
  content or setup preconditions are visible as one portfolio issue.
- Package-source validation should summarize manifest and package-lock
  alignment after Git UPM or package-source changes.
- Editor-opened validation lanes need workspace side-effect accounting before
  closeout.

## Implemented Public MCP Outcomes

- Added `test-results-table` for persisted EditMode/PlayMode result artifacts.
- Added reusable test-result parsing and failure grouping helpers.
- Enhanced the multi-project GUI test subset runner with request ids, result
  paths, lifecycle churn flags, grouped failures, package-source closeout, and
  workspace side-effect summaries.
- Documented the test-result source-of-truth schema and portfolio closeout
  criteria.

## Sanitization Notes

Project names, portfolio composition, concrete request ids, local dirty-file
paths, and project-specific fixture failures were removed. The retained content
is the reusable public operator pattern.

## Final Verdict

This retro is complete for public MCP history. Private project test content and
local portfolio composition remain outside the public archive.
