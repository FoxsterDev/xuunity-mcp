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
- Live matrix smoke exposed a Unity 2021 compile-time API mismatch before
  release: `PackageInfo.FindForPackageName` is unavailable there. The fix uses
  a compatibility wrapper and a static guard against direct calls to newer APIs.
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
- Offline manifest mutation before opening Unity is the preferred Test
  Framework install path. In-editor Package Manager mutation remains useful,
  but should be treated as a narrow fallback for already healthy bridges.
- Existing Test Framework versions may be part of a project's own test setup.
  Treating old versions as a cautious upgrade path is safer than presenting
  every dependency change as a fresh install.
- Editing a shell runner while it is executing can corrupt the running shell's
  parse stream. Future live-matrix script changes should be made before a run or
  validated in a separate copy.

## Validation

- Host optional-capability tests passed.
- Parser/tool-surface tests passed.
- Static guards prove core package metadata and core sources do not depend on
  TestRunner APIs.
- Host tests cover already suitable dependency, too-old dependency upgrade, and
  Unity 6000 supported-with-upgrade-recommendation behavior.
- Full host validation passed: `scripts/testing/run_host_python_tests.sh`
  reported `123/123`.
- Live clean-project matrix passed package EditMode `6/6` and PlayMode `5/5` on
  `2021.3.58f1`, `2022.3.62f3`, `2022.3.67f2`, `6000.0.58f2`,
  `6000.0.61f1`, `6000.2.14f1`, and `6000.3.3f1`.
- `2021.3.45f2` is classified as `skipped/create_project_license_unavailable`
  before package import because Unity reports no valid editor license while
  creating a clean project.

## Follow-Up

- Re-run the full installed-editor matrix after the `2021.3.45f2` license is
  repaired if that editor must be release evidence.
- Verify `batch-editmode-tests` before install reports actionable guidance and
  after install runs the optional batch entrypoint.
- Do a separate Rider and VS Code MCP setup guide after validating their current
  MCP configuration UX.
