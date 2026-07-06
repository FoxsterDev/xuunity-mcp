---
name: release-ci-guardrails
description: XUUnity Light Unity MCP release, tag, and CI-failure guardrails; use for version bumps, release tags, GitHub Actions failures, and follow-up fixes after CI catches platform-only regressions.
---

# Release and CI Guardrails

Use this skill before creating a release/tag and whenever GitHub Actions reports
a platform-only failure.

## Release Checklist

1. Run release checks after the final edit, not before:
   - `python3 scripts/testing/check_release_version_consistency.py`
   - `python3 scripts/testing/check_release_docs_freshness.py`
   - `python3 scripts/testing/check_public_release_safety.py`
2. Run the host Python suite after the final edit:
   - `scripts/testing/run_host_python_tests.sh`
3. If docs/site files changed, run:
   - `scripts/testing/run_site_ui_checks.sh`
4. Clean generated artifacts before staging:
   - `node_modules`, `__pycache__`, `playwright-report`, `test-results`
5. Create the release commit before the annotated tag. If CI fails after a tag
   was created or pushed, prefer a follow-up fix commit unless the maintainer
   explicitly asks to retag.

## Windows CI Assumptions

- Do not assume `HOME`, `USERPROFILE`, `HOMEDRIVE`, or `HOMEPATH` exist in CI.
  `Path.home()` can raise `RuntimeError`. Code that only builds plans, reviews,
  helper targets, recovery commands, or optional config paths must use a safe
  fallback and must not crash when the host home directory is unavailable.
- Add a regression for home-sensitive code by clearing `os.environ` and mocking
  `Path.home()` to raise `RuntimeError("Could not determine home directory.")`.
- Do not compare raw platform path strings in tests. For structured payload paths
  that are not shell commands, compare separator-normalized suffixes or resolved
  `Path` equality.
- For shell-facing commands, do not normalize the assertion after the fact; assert
  that the emitted command already uses POSIX-safe separators and contains no
  unintended backslashes.

## CI Failure Fix Loop

1. Classify the failure as product bug, test bug, platform assumption, or release
   metadata drift.
2. Reproduce the exact failing test locally when possible.
3. Add or tighten a regression that simulates the platform invariant directly
   instead of relying on the current host OS to reproduce it.
4. Run the focused failing tests, then the relevant file-level suite, then the
   full host suite before committing.
5. Keep follow-up CI fixes small and separate from broad release/content edits.
