# XUUnity Light Unity MCP Devmode Validation

Date: `2026-05-23`
Status: `current for v0.3.78`

Use this document when changing the XUUnity Light Unity MCP host, server,
wrapper scripts, Unity package, package metadata, smoke runners, or package
source switching behavior.

## Rule

- Treat `devmode` as the local-package validation mode for MCP development.
- Validate MCP package changes through a consumer Unity project that resolves
  `com.xuunity.light-mcp` from the local `packages/com.xuunity.light-mcp`
  working tree.
- Project-specific smoke suites, compile matrices, scenario runs, and product
  PlayMode suites are useful additional evidence, but they do not replace the
  package-owned MCP regression lane.

## Required Closeout For Executable-Code Changes

After executable-code changes in this repo or its Unity package, run the
package-owned self-test lane before closeout:

```bash
templates/smoke/run_package_self_tests.sh \
  --project-root <UnityProjectRoot> \
  --mode all
```

The runner no longer carries a hand-maintained assembly filter. It derives the
run plan from the package source: every shipped test assembly whose tests carry
the selected mode's category and whose `versionDefines` capability dependencies
are installed in the consumer project. The plan is printed as `editmode_plan=`
and `playmode_plan=` on the `package-self-test-discovery` line, each planned
assembly runs as its own filtered request, and an assembly that contributes
zero tests fails the lane with
`package_self_tests_assembly_contributed_no_tests: assembly=<name>`.

This keeps capability-gated assemblies such as the uGUI EditMode/PlayMode and
TextMeshPro EditMode suites under execution proof without making uGUI or
TextMeshPro a hard package dependency: in a project without those packages they
drop out of the plan instead of failing the lane. Adding a new test assembly to
the package needs no runner edit, and it can no longer be silently skipped.

If the package self-test lane cannot run, report that as an explicit MCP
validation gap instead of calling the MCP change fully validated.

## Runner Behavior

- Unity discovers test assemblies inside an installed package only when the
  package name is listed in the consumer project's `Packages/manifest.json`
  `testables` array.
- The package self-test runner temporarily adds `com.xuunity.light-mcp` to
  `testables`, refreshes the project, runs the selected package tests, and
  restores the original manifest on exit.
- Do not leave a permanent `testables` change in a consumer project unless that
  project intentionally wants package tests visible during normal Test Runner
  use.

## Scope Notes

- Documentation-only changes do not require the package self-test lane unless
  they also change executable scripts, host code, Unity package code, asmdefs,
  package metadata that affects compilation, or validation runner behavior.
- Host Python/server changes should also run the host Python test suite when
  available.
- Shell runner changes should at least pass shell syntax validation before
  closeout.
