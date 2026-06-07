# Codex Client Templates

Status: `active`.

This folder contains merge-safe Codex config snippets for
`~/.codex/config.toml`.

Use these snippets when:

- Codex is the current host client
- the user explicitly wants Codex wired
- you have already shown a preflight review and the user approved the change

Important:

- Reuse an existing helper install under `${CODEX_TOOLS_HOME:-$HOME/.codex-tools}`
  if it already exists. Do not clone a fresh repo copy just to recreate the
  same local helper.
- Merge the `xuunity_light_unity` block into an existing `config.toml`. Do not
  overwrite unrelated MCP servers.
- Restart or refresh Codex MCP servers after changing `~/.codex/config.toml` if
  the current session does not hot-reload newly added servers.
- Client wiring alone does not prove a Unity project is ready. After wiring,
  verify the target project with `validate-setup`, `ensure-ready`, and
  `unity_status_summary`.

Snippets:

- `config.toml.snippet` for Linux/macOS
- `config.windows.toml.snippet` for native Windows
