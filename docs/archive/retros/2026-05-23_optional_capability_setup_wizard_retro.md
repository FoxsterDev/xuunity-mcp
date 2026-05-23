# Optional Capability Setup Wizard Retro

Date: `2026-05-23`
Status: `post-implementation retro`

## What Went Well

- The Test Framework work became a reusable optional-capability pattern instead
  of a one-off compatibility patch.
- The existing EditMode and PlayMode implementation stayed mostly intact; the
  stability-sensitive code moved behind an asmdef boundary rather than being
  rewritten.
- The setup wizard gives less capable agents a deterministic flow: discover,
  plan, apply with approval, validate, and install optional test support only
  when needed.
- Capability output now distinguishes core health from optional feature
  readiness.
- The setup wizard now distinguishes missing Test Framework, already suitable
  Test Framework, too-old existing Test Framework, and supported-but-upgrade-
  recommended versions.
- The self-review pass caught a bad intermediate choice: a new global
  `healthy_with_unsupported_capabilities` status would have broken existing
  readiness checks that expect core health to be `healthy`.

## What Was Risky

- Unity asmdef Version Defines are the critical behavior. Host tests can inspect
  JSON, but only live Unity imports prove the optional assembly compiles exactly
  as intended.
- Moving files without preserving `.meta` GUIDs would have created noisy Unity
  asset churn. The implementation preserved the old test-operation `.meta`
  files and added `.meta` files for new assets.
- Package Manager mutation is useful for approved Test Framework install, but
  must remain narrow and explicit.
- Existing Test Framework versions may be part of a project's own test setup.
  Treating old versions as a cautious upgrade path is safer than presenting
  every dependency change as a fresh install.

## Validation

- Host optional-capability tests passed.
- Parser/tool-surface tests passed.
- Static guards prove core package metadata and core sources do not depend on
  TestRunner APIs.
- Host tests cover already suitable dependency, too-old dependency upgrade, and
  Unity 6000 supported-with-upgrade-recommendation behavior.
- Full host validation passed: `scripts/testing/run_host_python_tests.sh`
  reported `115/115`.

## Follow-Up

- Run the live Unity matrix for 2021.3, 2022.3, and 6000.x with and without
  Test Framework.
- Verify `batch-editmode-tests` before install reports actionable guidance and
  after install runs the optional batch entrypoint.
- Do a separate Rider and VS Code MCP setup guide after validating their current
  MCP configuration UX.
