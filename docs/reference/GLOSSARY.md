# Glossary

Date: `2026-05-23`
Status: `current for v0.3.37`

## XUUnity

XUUnity is the surrounding AI-assisted Unity workflow system used by this project. The MCP service can also be consumed as a standalone Unity Editor automation layer.

## MCP

MCP means Model Context Protocol. It lets AI clients call structured tools exposed by a local or remote server.

## Host-Side MCP Server

The host-side server is the local process that speaks MCP to AI clients and routes requests to a Unity project.

## Unity Package

The Unity package is `com.xuunity.light-mcp`. It contains the editor-side bridge and editor-only operations used by the host-side MCP server.

Current production Git UPM path:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.37
```

## Git UPM

Git UPM is Unity Package Manager installing a package directly from a Git URL.
It is the current production install route for this package until OpenUPM is
published.

## OpenUPM

OpenUPM is a public Unity package registry. XUUnity Light Unity MCP has a
registry-native package path, but the documented install route is still Git UPM
until an OpenUPM package page exists.

## devmode

`devmode` points a consumer Unity project at the local package folder for MCP
package development.

## prodmode

`prodmode` points a consumer Unity project at a published Git package source.
It pins the package to the published release tag that matches the package
version so release-bound projects do not depend on local-only package changes.

## Optional Capability

An MCP feature that may be `supported`, `unsupported`,
`disabled_missing_dependency`, `disabled_dependency_too_old`, `degraded`, or
`error` without making the core MCP health fail.

## Test Framework Capability

The optional EditMode and PlayMode test surface backed by
`com.unity.test-framework`. Unity enables it through asmdef Version Defines
when `XUUNITY_LIGHT_MCP_TESTS_CAPABILITY` is available.

## BridgeRegistry

BridgeRegistry is the local routing layer used to map MCP requests to the correct Unity project/editor instance on the same host.

## ProjectContext

ProjectContext is the host-side state for a single Unity project, including project paths, bridge state, editor session evidence, and request routing metadata.

## Same-Host Editor Automation

Same-host automation means the AI client, MCP server, and Unity Editor run on the same trusted machine or CI host.

## Request Journal

The request journal is the per-project record under
`Library/XUUnityLightMcp/journal/requests/` used to recover final request status
after Unity reloads, transport churn, or wrapper timeouts.

## Scenario

A scenario is a bounded JSON workflow that asks Unity MCP to perform ordered validation steps such as refresh, compile, Play Mode, scene checks, screenshots, or project-defined hooks.
