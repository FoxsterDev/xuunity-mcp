# XUUnity Light MCP Unity Package

Date: `2026-07-01`
Status: `current for package v0.3.40`

This Unity package provides the editor-side bridge for the lightweight
XUUnity Light Unity MCP service.

Author:
- Siarhei Khalandachou
- LinkedIn: `https://www.linkedin.com/in/khalandachou/`

It is intended to be:

- editor-only
- removable
- disabled by default
- safe to consume from more than one repo

## Install

Add this to `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.40"
  }
}
```

## What This Package Does

This package exposes the Unity-side bridge for:

- status
- capability probe
- console tail
- console grep and compact loading-timing evidence
- scene snapshot
- EditMode tests when the optional Test Framework capability is available
- PlayMode tests when the optional Test Framework capability is available
- compile validation and compile matrices without switching the active build target
- plain BuildPipeline player builds through the editor bridge
- play mode control
- Game View control and screenshots
- scenario validation, execution, and persisted results
- project-defined scenario hooks through `IXUUnityLightMcpScenarioHook`
- catalog-backed `project_action` scenario steps
- poll-until hook scenarios for project-defined acceptance checks
- compact scenario verdicts for agent acceptance checks, with verbose payloads
  reserved for deep diagnostics

Refresh, compile, build-config compile, and direct test responses preserve
authoritative post-settle result fields for host-side compact MCP summaries.
Full raw bridge payloads remain available through the host server's documented
full-payload opt-in.

Before EditMode and PlayMode test execution, the package runs a best-effort
test preflight that closes Unity Android Logcat editor windows when they are
open. This avoids Android Logcat background `adb devices` polling noise during
automated validation. The preflight uses type-name lookup only, so it has no
hard dependency on the Android Logcat package and does nothing when that
package or window is absent.

The core package has no hard dependency on `com.unity.test-framework`. Test
operations are compiled by the optional Test Framework assembly when Unity
asmdef Version Defines set `XUUNITY_LIGHT_MCP_TESTS_CAPABILITY`.
Existing Test Framework dependencies are preserved unless an approved setup
step updates them. Versions below `1.1.33` disable test capability and should be
upgraded carefully; Unity 6000 projects on `1.1.33` remain supported but may
receive an optional recommendation to move to `1.5.1`.

The host-side MCP server is not inside this package.
It must be installed separately on the machine that runs the AI client.

## License

This package is MIT-licensed and provided as-is, without warranty or liability.

See:
- `../../../LICENSE`

## Next Read

- `../../../docs/agents/AI_INTEGRATION.md`
