# Security Model

Date: `2026-05-23`
Status: `current for v0.3.24`

XUUnity Light Unity MCP is designed as a local same-host Unity Editor automation service.

Default safety choices:

- editor-only Unity package
- disabled by default
- explicit per-project enablement
- no runtime/player support in the base package
- no dynamic Roslyn execution path
- no SignalR or external relay stack
- no secrets required by the Unity package
- no project settings mutation during normal install path
- capability-gated operations
- request artifacts stored under the Unity project `Library` folder
- production package consumed through a pinned Git UPM release path unless the
  project intentionally switches into local `devmode`

## Threat Model

This project is intended for trusted local development machines and trusted CI agents.

It is not intended to:

- expose Unity Editor control to untrusted networks
- operate as a remote public service
- provide multiplayer runtime control
- automate player builds at runtime
- execute arbitrary user-provided C# through a dynamic compiler path

## Operational Guidance

- Keep the bridge disabled until Unity-aware validation is needed.
- Enable the bridge per project, not globally.
- Treat AI clients as trusted local operators.
- Review scenario files before running them against sensitive projects.
- Do not store credentials in bridge configs or scenario files.
- Use `prodmode` or an explicit Git UPM tag for publishable project state.
- Use `devmode` only for local MCP package iteration.

## License And Operational Responsibility

This project uses the MIT License. See [LICENSE](LICENSE) for the canonical
license text.

Practical operating note:

- this software is free to use
- the author provides it without operational guarantees
- you are responsible for how you apply it to repos, projects, builds, devices,
  and automation flows

## Reporting Security Issues

Open a private issue or contact the maintainer directly before publishing details for a vulnerability that could expose local projects, credentials, or build artifacts.
