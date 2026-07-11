# Contributing to XUUnity MCP

Thanks for helping improve XUUnity MCP. Contributions to code, tests,
documentation, setup flows, and reproducible bug reports are welcome.

By participating, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Before You Start

- Search existing issues and discussions before opening a new one.
- Use the issue forms and provide a minimal, sanitized reproduction.
- For install or runtime failures, follow the retro guidance in
  [Opening A Useful Issue](README.md#opening-a-useful-issue).
- Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
- Do not publish credentials, private project details, proprietary assets, or
  unrelated logs.

For a substantial feature or a behavior-changing proposal, open a feature
request first so the scope and compatibility requirements can be agreed on
before implementation.

## Development Setup

The core host helper uses Python's standard library and supports the platforms
covered by CI. Use Python 3.11 or newer for local validation.

```bash
git clone https://github.com/FoxsterDev/xuunity-mcp.git
cd xuunity-mcp
PYTHONPATH=templates python -m unittest discover -s tests -v
```

Changes to the public documentation site also require Node.js:

```bash
npm ci
npx playwright install chromium
npm run test:site:ui
```

See [INSTALL.md](INSTALL.md) for product installation and
[the smoke-test guide](docs/operations/SMOKE_TESTS.md) for Unity-aware and
end-to-end validation.

## Making Changes

1. Create a focused branch from `master`.
2. Keep changes small and avoid unrelated formatting or refactors.
3. Preserve macOS, Linux, Windows, and Windows Git Bash compatibility.
4. Add or update tests for behavior changes.
5. Update user-facing documentation and `CHANGELOG.md` when applicable.
6. Run the validation relevant to every area you changed.

Public examples must remain generic and safe to share. Never add local machine
paths, host-private repository names, credentials, or assumptions about a
specific Unity project.

## Validation

Run the Python suite for changes to the host helper, launchers, setup flows,
templates, or protocol behavior:

```bash
PYTHONPATH=templates python -m unittest discover -s tests -v
```

For documentation or site UI changes, also run:

```bash
npm run test:site:ui
```

For Unity package, lifecycle, build, or scenario changes, run the narrowest
relevant smoke suite documented in
[docs/operations/SMOKE_TESTS.md](docs/operations/SMOKE_TESTS.md), and state the
Unity version and platform used in the pull request.

## Pull Requests

A pull request should:

- explain the problem and the chosen solution
- link the related issue when one exists
- describe user-visible and compatibility impact
- list the exact validation performed and its result
- include sanitized logs or screenshots when they materially help review
- call out validation that could not be run
- contain no secrets, generated test artifacts, or private project data

Maintainers may ask for a smaller scope, additional platform coverage, or
changes to preserve the project's safety and compatibility contracts.

## License

By contributing, you agree that your contribution is licensed under the
project's [MIT License](LICENSE).
