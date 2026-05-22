# Glossary

## XUUnity

XUUnity is the surrounding AI-assisted Unity workflow system used by this project. The MCP service can also be consumed as a standalone Unity Editor automation layer.

## MCP

MCP means Model Context Protocol. It lets AI clients call structured tools exposed by a local or remote server.

## Host-Side MCP Server

The host-side server is the local process that speaks MCP to AI clients and routes requests to a Unity project.

## Unity Package

The Unity package is `com.xuunity.light-mcp`. It contains the editor-side bridge and editor-only operations used by the host-side MCP server.

## BridgeRegistry

BridgeRegistry is the local routing layer used to map MCP requests to the correct Unity project/editor instance on the same host.

## ProjectContext

ProjectContext is the host-side state for a single Unity project, including project paths, bridge state, editor session evidence, and request routing metadata.

## Same-Host Editor Automation

Same-host automation means the AI client, MCP server, and Unity Editor run on the same trusted machine or CI host.

## Scenario

A scenario is a bounded JSON workflow that asks Unity MCP to perform ordered validation steps such as refresh, compile, Play Mode, scene checks, screenshots, or project-defined hooks.

