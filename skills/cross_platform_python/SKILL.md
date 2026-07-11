---
name: cross-platform-python
description: Rules for Python host code (templates/*.py, root launchers, tests) so every change runs identically on Windows, Ubuntu, and macOS the first time — host detection, path flavor, subprocess discipline, UTF-8, process replacement, and platform-portable test expectations.
---

# Cross-Platform Python Guidelines

The Python host runs on macOS daily and on Windows/Linux only when a colleague or CI executes it. Every rule below was earned from a real Windows failure that macOS could not reproduce (2026-07 deep review: `docs/archive/reports/2026-07-10_windows_platform_deep_review.md`). Load this skill before writing or editing any Python in `templates/`, the root `*.py` launchers, or tests.

---

## 1. Host Detection Goes Through `server_core`

- `server_core.is_windows_like_host()` for user-facing flavor decisions (rendered commands, launcher names, quoting). It is env-based and covers native cmd/PowerShell, MSYS/Git Bash, and Cygwin — `os.name` alone does not.
- `server_host_platform.host_platform_kind()` for adapter routing (process listing, liveness).
- Never branch on `sys.platform == "darwin"` as an implicit "POSIX else Windows" split; Linux must land in the POSIX branch deliberately.

## 2. Path Flavor Is Part of the Contract

- Shell-facing strings: `server_core.quoted_shell_path()` / `render_launcher_cli()` — native form + quotes on Windows-like hosts, `as_posix()` elsewhere. Never embed bare `str(path)` in a command template (see cross-platform-shell skill rule 8).
- Preserve `PurePath` flavor in helpers: wrapping an incoming `PureWindowsPath` in `Path(...)` on a POSIX host silently rewrites separators.
- Durable values read later by native Windows tools must be host-native; values read by Git Bash must be POSIX (cross-platform-shell skill rule 7).

## 3. Subprocess Discipline (enforced by AST sweep)

Every helper spawn (`tasklist`, `taskkill`, PowerShell, `ps`, `lsof`, `wslpath`, `git`, `open`, refresh helpers) must pass:

- `timeout=` — a hung probe otherwise blocks the MCP server forever with zero diagnostics;
- explicit `subprocess.TimeoutExpired` handling — it is **not** an `OSError`; an `except OSError` guard silently lets the timeout escape and crash the caller (this bug shipped in the PowerShell process-listing path);
- `encoding="utf-8", errors="replace"` — never locale/ANSI decode (cp1251/cp866 hosts corrupt output);
- `**server_core.hidden_window_subprocess_kwargs()` when the spawn can run on a Windows host — GUI-hosted servers must not flash console windows.

The only legitimate no-timeout spawns are children that ARE the workload (delegated server run, batch self-invocations). `tests/test_subprocess_timeout_contract.py` sweeps every `subprocess.run` call via AST and holds the explicit allowlist — extend the allowlist consciously; never drop `timeout=` silently.

## 4. UTF-8 End to End

- Call `server_core.reconfigure_stdio_utf8()` first in every Python entrypoint; Windows pipes default to the ANSI codepage and a Cyrillic project path kills stdio mid-decode otherwise.
- Launchers default `PYTHONUTF8=1`; keep protocol JSON `ensure_ascii=True`.
- File reads accept BOM/UTF-16 where the writer may be PowerShell (`server_core.read_json`).

## 5. `os.execv` Is POSIX-Only Behavior

On Windows `os.execv` spawns a new process and kills the parent — an MCP client watching the parent sees its server die. On `os.name == "nt"` use `subprocess.run` and propagate the exit code (`exec_python_script`, refresh `exec_run` are the reference shape).

## 6. Files Other Processes Poll Are Published Atomically

Use `server_core.write_json` (temp + `os.replace`) for anything the editor or another process polls. Never ad-hoc `open(...).write` for polled files. Full co-design rules: atomic-ipc-files skill.

## 7. POSIX-Only Tools Need a Windows Answer

`lsof`, `ps`, `open` have no Windows presence. Any feature built on them needs a Windows counterpart (`tasklist`, CIM listing, Hub `secondaryInstallPath.json` discovery) or a documented safe degradation — silent `[]` on Windows turns a safety check into a no-op.

## 8. Platform-Portable Test Expectations

Windows CI failures from this repo's history were mostly test-pinning bugs, not product bugs. When writing tests:

- Pin the flavor when asserting rendered commands: `mock.patch.object(server_core, "is_windows_like_host", return_value=False)` — otherwise the Windows leg correctly renders `.cmd` + native paths and the assert breaks.
- Derive path expectations from the platform: expect `str(Path("/x/y"))`, not a hard-coded `"/x/y"`.
- Case-insensitive usage asserts: the wrapper prints `Usage:`, argparse prints `usage:` — compare on `.lower()`.
- Never compare full path strings (cross-platform-shell skill rule 9).
- Patch through the facade, call through the facade: `server_editor_host` re-syncs owner modules per call; patches applied via the facade leak into owner modules until the next facade call, so direct owner-module calls in later tests see stale mocks (`tests/test_subprocess_timeout_contract.py` TaskkillContractTest documents the shape).
- New cross-module name in a star-import module: verify it resolves in the defining module (`hasattr` probe) AND add a test that executes the new call path — a latent `NameError` on an untested branch passed a 340-test suite here once (`render_launcher_cli` in the lifecycle module).
