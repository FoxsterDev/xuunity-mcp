# XUUnity Light Unity MCP

XUUnity Light Unity MCP is an open-source, lightweight Model Context Protocol server for Unity Editor automation.

It lets MCP-compatible AI clients such as Cursor, Claude Code, Claude Desktop, Codex-style agents, and custom LLM agents inspect and control Unity projects through a small editor-only Unity package and a local host-side MCP server.

The project is designed for production Unity workflows where safety matters: compile checks, EditMode and PlayMode tests, scene inspection, console logs, build target validation, Game View screenshots, and recovery after Unity Editor lifecycle churn.

Unlike broader Unity MCP implementations, XUUnity Light Unity MCP is editor-only by default, disabled until explicitly enabled per project, removable, and does not add runtime/player build footprint by default.

## Why Use It

Use it when you want a small, local-first Unity MCP surface for validation-heavy workflows rather than broad unrestricted editor mutation.

Good fits:

- Unity Editor status and health checks
- Unity console tail
- scene snapshot and scene assertions
- EditMode and PlayMode test execution
- player script compile validation
- compile matrix across build targets and scripting defines
- build target get/switch
- Game View configuration and screenshots
- bounded scenario validation and scenario runs
- same-host multi-project routing

## Quick Start

Add the Unity package to `Packages/manifest.json`:

```json
{
  "dependencies": {
    "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-light-unity-mcp.git?path=/templates/unity-package#v0.3.10"
  }
}
```

Install the host-side MCP helper:

```bash
bash init_xuunity_light_unity_mcp.sh
```

Enable the bridge for a Unity project:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --project-root /path/to/UnityProject \
  --enable-project
```

For complete setup, see [INSTALL.md](INSTALL.md).

## Supported Clients

- [Cursor](docs/clients/cursor.md)
- [Claude Code](docs/clients/claude-code.md)
- [Claude Desktop](docs/clients/claude-desktop.md)
- [Windsurf](docs/clients/windsurf.md)
- [Codex-style agents](docs/clients/codex.md)
- custom MCP-compatible agents

## Safety Model

- editor-only Unity package
- disabled by default
- explicit per-project enablement
- no player build footprint by default
- no runtime/player automation in the base package
- no dynamic Roslyn execution path
- no SignalR or external relay stack
- capability-gated operations

See [SECURITY.md](SECURITY.md) for the threat model.

## Documentation

- [Install](INSTALL.md)
- [Features](FEATURES.md)
- [AI integration](AI_INTEGRATION.md)
- [Security model](SECURITY.md)
- [Comparison](COMPARISON.md)
- [Discovery guide](DISCOVERY.md)
- [Glossary](GLOSSARY.md)
- [Current implementation status](STATUS.md)
- [Build automation](BUILD_AUTOMATION.md)
- [Smoke tests](SMOKE_TESTS.md)
- [Roadmap](ROADMAP.md)

## Package

Unity package id:

```text
com.xuunity.light-mcp
```

Current package version:

```text
0.3.10
```

Package folder:

```text
templates/unity-package
```

## License

MIT. See [LICENSE](LICENSE) and [LICENSE.md](LICENSE.md).
