# Claude Code Client Adapter

Status: `active`.

Claude Code talks to MCP servers over stdio. The lightweight Unity MCP service
ships an installable stdio launcher (`run.sh`) that Claude Code consumes
directly. The Claude-side install lives in its own directory and is fully
independent from any other agent.

## Install Layout (Claude-Side)

```
~/.claude-tools/
└── xuunity-light-unity-mcp/
    ├── run.sh          # self-resolving stdio launcher
    ├── server.py       # MCP server
    └── server_*.py     # helper modules
```

This is symmetric to `~/.codex-tools/xuunity-light-unity-mcp/` (used by Codex)
but **independent** — you can have Claude Code without Codex, or both, or
either alone. Neither install references the other.

Override path with `CLAUDE_TOOLS_HOME` if you want a non-default location.

## What This Folder Provides

- `.mcp.json` — project-scope snippet with metadata pointing to AI integration guides. Drop at the repo root (`<repo>/.mcp.json`)
  and Claude Code picks it up automatically the next time `claude` is launched
  from that repo. Project-scope config is checked into git, so the whole team
  inherits it after `git pull`.

- `.claude/rules/unity-mcp-test-execution.md` — Claude Code rules file with best practices for Unity test execution via MCP.
  This file is automatically loaded in every Claude Code session when placed at `<repo>/.claude/rules/`.

## Install Routes

### 1. Install the Claude-side server (one-time)

```bash
bash init_xuunity_light_unity_mcp.sh \
  --target claude
```

This drops the server into `~/.claude-tools/xuunity-light-unity-mcp/`. Does
not touch `~/.codex-tools/`. Does not touch any Codex config.

To install both sides at once:

```bash
bash init_xuunity_light_unity_mcp.sh \
  --target both
```

### 2. Register the MCP server with Claude Code

Three scope options. Pick by intent.

#### Project scope (team-wide, under git)

Recommended for monorepos. Copy the configuration files to the repo root on Linux/macOS:

```bash
cp templates/clients/claude-code/.mcp.json .mcp.json
cp -r templates/clients/claude-code/.claude .claude
```

Native Windows:

```powershell
Copy-Item templates\clients\claude-code\.mcp.windows.json .mcp.json
Copy-Item -Recurse templates\clients\claude-code\.claude .claude
```

Then commit `.mcp.json` and `.claude/` directory. Every team member running `claude` from the repo root
gets the same MCP server registration and AI behavior rules. On first launch Claude Code asks the
user to approve the project-scoped server; that approval is per-user and is
not shared.

#### User scope (single-user, all projects)

```bash
bash init_xuunity_light_unity_mcp.sh \
  --target claude \
  --install-claude-config
```

Adds the `xuunity_light_unity` server block to `~/.claude.json`
(`mcpServers`) without touching any repo.

#### Local scope (one user, one project, ad hoc)

```bash
claude mcp add --scope local --transport stdio xuunity_light_unity \
  -- bash -lc 'exec "${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}/xuunity-light-unity-mcp/run.sh"'
```

## How To Verify

In a fresh Claude Code session opened from the repo root:

```bash
claude mcp list
```

Expected line:

```
xuunity_light_unity: bash -lc exec "${CLAUDE_TOOLS_HOME:-$HOME/.claude-tools}/xuunity-light-unity-mcp/run.sh"  - Connected
```

A failed connect typically means the Claude-side server was never installed
(run `init --target claude`) or `run.sh` is not executable.

## Available MCP Tools

When connected, Claude Code sees the standard XUUnity stdio tools — see
`../../../docs/reference/FEATURES.md` for the canonical inventory.

Useful first-pass tools for any Unity work:

- `unity.status`
- `unity.capabilities.get`
- `unity.health.probe`
- `unity.console.tail`
- `unity.scene.snapshot`
- `unity.compile.player_scripts`
- `unity.tests.run_editmode`

Follow the recommended first-validation pass in `../../../docs/agents/AI_INTEGRATION.md`.

## Agent Behavior Rules

When Claude Code runs Unity work in this repo through MCP, it should follow
the same rules listed in `../../../docs/agents/AI_INTEGRATION.md` — "Agent Behavior Rules" and
"Startup Policy". They are agent-agnostic; this template only wires the
transport.

## Boundary Notes

- The MCP server is per-project: each tool call must pass `--project-root` to
  the target Unity project (the server does not assume one).
- The repo router (`Agents.md`) requires validation to go through MCP for
  Unity-aware lanes; do not fall back to direct `unity -batchmode` /
  `-runTests` from a shell tool just because Unity is installed locally. If your
  host repo defines local validation-boundary guidance, follow that guidance.
- Project-scope `.mcp.json` requires user approval on first launch. That is
  Claude Code's built-in safeguard; it cannot be auto-approved by the snippet.
- The Claude-side install (`~/.claude-tools/`) is fully independent from any
  Codex-side install (`~/.codex-tools/`). Removing or upgrading one does not
  affect the other.
