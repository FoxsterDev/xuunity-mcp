# Package Path Migration

Date: `2026-05-23`
Status: `current for v0.3.20`

XUUnity Light Unity MCP moved the Unity package to a registry-native path for
OpenUPM and Unity Package Manager indexing.

## Old Path

```text
templates/unity-package
```

This path is valid for projects pinned to `v0.3.11`.

## New Path

```text
packages/com.xuunity.light-mcp
```

Use this path for `v0.3.12+`.

## Git UPM URL

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.20
```

## Local Development Path

```text
file:/absolute/path/to/xuunity-mcp/packages/com.xuunity.light-mcp
```

## Migration Steps

1. Replace `?path=/templates/unity-package#v0.3.11` with
   `?path=/packages/com.xuunity.light-mcp#v0.3.20`.
2. Remove the `com.xuunity.light-mcp` entry from `Packages/packages-lock.json`
   or let `xuunity_light_unity_mcp.sh prodmode` do it.
3. Let Unity re-resolve packages by reopening the project or refreshing the
   project.
4. Run `request-status-summary`, compile validation, or the batch compile
   matrix before committing the project reference change.

Projects that intentionally stay on `v0.3.11` do not need to change.
