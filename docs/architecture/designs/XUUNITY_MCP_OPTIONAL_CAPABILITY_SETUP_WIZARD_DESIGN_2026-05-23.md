# XUUnity MCP Optional Capability Setup Wizard Design

Date: `2026-05-23`
Status: `implemented; host-validated`

## Summary

This pass makes optional capability architecture the default pattern for
package-backed MCP features. A missing optional dependency must not break core
MCP readiness. It should produce a precise capability status, recommended
action, and approved install path.

The first reference implementation is Unity Test Framework support:

- core MCP works without `com.unity.test-framework`
- EditMode and PlayMode operations live in an optional assembly
- Unity enables that assembly with asmdef Version Defines
- setup tooling recommends dependency versions per Unity project

## Public Interfaces

Host CLI:

- `setup-plan --workspace-root PATH [--project-root PATH ...] [--recursive]`
- `setup-apply --plan-file PATH --yes`
- `validate-setup --project-root PATH [--include-tests]`
- `install-test-framework --project-root PATH --yes [--version VERSION]`
- `request-install-test-framework --project-root PATH --yes [--version VERSION]`

MCP tools:

- `xuunity_setup_plan`
- `xuunity_setup_apply` with `approve: true`
- `xuunity_setup_validate`
- `unity_package_install_test_framework` with `approve: true`

Capability statuses:

- `supported`
- `unsupported`
- `disabled_missing_dependency`
- `disabled_dependency_too_old`
- `degraded`
- `error`

## Optional Feature Capability Pattern

Use this pattern whenever a feature depends on a Unity package, editor version,
platform module, or optional project package:

1. Keep core operations and health probes free of optional package references.
2. Put dependency-backed code in a separate asmdef.
3. Gate that asmdef with `defineConstraints`.
4. Use asmdef `versionDefines` to set the canonical feature define.
5. Register optional operations and capability providers from the optional
   assembly when it compiles.
6. Keep known optional operations in the core capability registry so missing
   optional operations return actionable capability errors, not generic unknown
   operation errors.
7. Report dependency, installed version, minimum version, recommended version,
   recommendation basis, and recommended action.
8. Never mutate manifests unless the caller gives explicit approval.

For Unity Editor API availability, use Unity's built-in version symbols when
the compatibility boundary is known, for example `UNITY_2021_3_OR_NEWER`,
`UNITY_2022_3_OR_NEWER`, or `UNITY_6000_0_OR_NEWER`. If the exact API boundary
is not known or spans package-manager implementation differences, use a narrow
reflection/fallback helper and cover it with a static compatibility test.

Reference Test Framework gate:

```json
{
  "defineConstraints": ["XUUNITY_LIGHT_MCP_TESTS_CAPABILITY"],
  "versionDefines": [
    {
      "name": "com.unity.test-framework",
      "expression": "1.1.33",
      "define": "XUUNITY_LIGHT_MCP_TESTS_CAPABILITY"
    }
  ]
}
```

## Compatibility Policy

The minimum Test Framework capability gate remains `>= 1.1.33`.

Recommendations:

| Unity version | Recommended dependency |
| --- | --- |
| Unity 2021/2022 | `com.unity.test-framework@1.1.33` |
| Unity 6000+ | `com.unity.test-framework@1.5.1` |

Unity 6000 with Test Framework `1.1.33` can be capability-supported, but reports
`upgrade_recommended=true` toward `1.5.1`.

Existing Test Framework dependencies are classified explicitly:

- missing dependency -> optional install action
- installed `>= 1.1.33` and at the Unity-version recommendation -> supported,
  no action
- installed `>= 1.1.33` but below the Unity-version recommendation -> supported
  with optional upgrade guidance
- installed `< 1.1.33` -> `disabled_dependency_too_old`, cautious approved
  upgrade action

The wizard must never silently rewrite an existing Test Framework version. It
may plan an upgrade, but apply still requires explicit approval and the result
must tell the operator to let Unity resolve packages and revalidate compile/test
behavior.

## Implementation Checklist

- [x] Package metadata changed to Unity `2021.3`.
- [x] Hard `com.unity.test-framework` dependency removed from package metadata.
- [x] Core asmdef no longer references TestRunner assemblies.
- [x] Optional Test Framework asmdef added with Version Defines.
- [x] Test operations and TestRunner utilities moved into optional assembly.
- [x] Core registry keeps known test operations and reports capability errors.
- [x] Health report includes optional capability status and dependency guidance.
- [x] Host setup wizard discovers single, flat, mixed-version, and nested roots.
- [x] Existing Test Framework dependencies are classified as suitable, too old,
  or supported with optional upgrade recommendation.
- [x] Host and MCP install flows require explicit approval.
- [x] Batch EditMode test lane fails early with actionable capability guidance.
- [x] Docs and plan history updated.

## Validation Evidence

- `python3 -m unittest tests.test_setup_wizard -v` passed 9 tests.
- `python3 -m unittest tests.test_server_protocol_and_parser -v` passed 21 tests.
- `scripts/testing/run_host_python_tests.sh` passed 123 tests.
- Static tests verify package metadata has no hard Test Framework dependency.
- Static tests verify the core asmdef and core editor sources do not reference
  TestRunner APIs.
- Policy tests verify Unity 2021/2022/6000 Test Framework recommendations.
- Live clean-project matrix passed package EditMode `6/6` and PlayMode `5/5` on
  `2021.3.58f1`, `2022.3.62f3`, `2022.3.67f2`, `6000.0.58f2`,
  `6000.0.61f1`, `6000.2.14f1`, and `6000.3.3f1`.
- `2021.3.45f2` is classified as
  `skipped/create_project_license_unavailable` on this host because Unity
  cannot create a clean project before package import without a valid editor
  license.

## Self-Review

What looks good:

- The old test execution logic stayed materially intact; the main change is the
  assembly boundary and registration path.
- Core package import no longer depends on Test Framework, which improves UX for
  Unity 2021/2022/6000 mixed hubs.
- Setup planning is per project and avoids one global dependency version.
- Already-installed Test Framework versions are no longer collapsed into a
  generic install path; the plan reports install versus upgrade intent.
- Missing test support is now an expected capability state instead of a global
  health failure.
- Self-review caught that introducing a new global health status for disabled
  optional features would break existing readiness checks; the final behavior
  keeps core health as `healthy` and carries optional state in capability
  records.

Risks:

- Unity asmdef Version Defines behavior should be live-smoked across the target
  Unity versions because it is the critical compile boundary.
- Test assembly references and optional assembly registration need live Unity
  domain reload verification before tagging.
- `install-test-framework` should be the default Test Framework install route:
  mutate `Packages/manifest.json` offline before opening Unity, preserve newer
  existing Test Framework versions, and then let Unity resolve packages during
  normal startup.
- `request-install-test-framework` mutates package state through Package
  Manager; keep it audited, require explicit approval, and reserve it for
  already healthy bridges.
- Supported-but-not-recommended versions, such as Unity 6000 with Test
  Framework `1.1.33`, can still be surprising to operators. The status must
  stay non-blocking while the upgrade recommendation remains visible.

Follow-up:

- Run the Unity 2021.3/2022.3/6000.x matrix with and without Test Framework.
- Add client-specific setup wizard docs for Rider and VS Code after a separate
  IDE MCP setup deep dive.
- Consider generating a setup plan file path automatically if operators want a
  one-command plan artifact flow.
