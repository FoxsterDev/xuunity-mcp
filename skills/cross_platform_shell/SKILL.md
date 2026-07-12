---
name: cross-platform-shell
description: Rules for bash scripts, wrappers, and CI steps in this repo that must run identically on macOS, Linux, and Windows Git Bash (MSYS), plus native cmd launcher flavor rules and the bisection workflow for hangs that reproduce only in CI.
---

# Cross-Platform Shell Guidelines

This repo's shell entrypoints (`xuunity_light_unity_mcp.sh`, `templates/run.sh`, `scripts/testing/*.sh`) are executed on macOS, Linux, and Windows Git Bash. Every rule below was earned from a real silent-hang incident on Windows CI. Violating them produces hangs with zero output that eat the whole CI job time limit.

---

## 1. Path Walks Terminate on a Fixed Point, Never on `/`

On Windows, `pwd`/paths can take forms like `D:/a/repo` or `D:\a\repo`. A `dirname` descent walks `D:/a → D: → . → .` and **never reaches `/`** — the loop spins forever inside `$(...)` with no output.

```bash
# INCORRECT (infinite loop on Windows path forms)
while [[ "$candidate" != "/" ]]; do
  candidate="$(dirname "$candidate")"
done

# CORRECT (terminates on any path form: /, //, D:, .)
local previous_candidate=""
while [[ -n "$candidate" && "$candidate" != "$previous_candidate" ]]; do
  previous_candidate="$candidate"
  candidate="$(dirname "$candidate")"
done
```

## 2. Resolve Git Bash Explicitly When Spawning From Native Code

`subprocess.run(["bash", ...])` from Python on Windows resolves through CreateProcess search order to the **System32 WSL stub**, not Git Bash. Use `tests/bash_support.py:resolve_bash_executable()` — it prefers `Git/usr/bin/bash.exe` (the real binary) over the `Git/bin` shim, which also makes process-tree kill reliable.

## 3. No `xargs -P` Under MSYS

Parallel `xargs` is unreliable under MSYS fork emulation (known upstream hangs). The runner scripts branch to a sequential in-process `run_worker` loop when `OSTYPE` is `msys`/`cygwin` or parallelism ≤ 1. Keep that branch when editing them.

## 4. Line Endings Are Enforced by `.gitattributes`

Windows CI runners check out with `core.autocrlf=true`. The repo's `.gitattributes` pins `*.sh`/`*.py`/`*.json` to LF and `*.cmd`/`*.ps1` to CRLF. Never remove it; new text file types should be added there.

## 5. Normalize Backslash Interpreter Paths

Env vars like `PYTHON` may arrive as `C:\...\python.exe`. Convert `\` → `/` before `command -v` or exec (see `resolve_python_bin` in the wrapper). Runner scripts accept an explicit `XUUNITY_LIGHT_UNITY_MCP_PYTHON` override; tests pass `Path(sys.executable).as_posix()`.

## 6. Keep MCP Shell Entry Points Thin

Root MCP `.sh` entrypoints must be process launchers, not implementation
containers. They may resolve their own directory, normalize the Python
interpreter, set launcher metadata, and `exec` Python. Version parsing,
source-root discovery, install refresh, process management, JSON editing,
project traversal, retries, and recovery policy belong in Python modules with
tests. This rule is especially strict for Windows Git Bash compatibility.

## 7. Persist Host-Native Paths For Native Readers

If a Git Bash/MSYS installer writes a durable path marker or config value that
native Windows Python, cmd, or PowerShell will read later, write a host-native
path with `cygpath -w` or make the reader explicitly convert MSYS paths.
Persisted text is not converted by the MSYS process-launch layer.

## 8. Shell-Facing Command Strings Use POSIX Paths

Any command string printed for a human, agent, log, JSON payload, recovery
hint, or copy/paste shell invocation must be stable for Git Bash. Do not embed a
`Path` object or `str(path)` directly in a command template; on Windows that can
produce backslashes like `\tmp\Project`, which Git Bash treats differently from
the intended `/tmp/Project`.

```python
# INCORRECT (Windows can render backslashes in shell-facing text)
f"xuunity_light_unity_mcp.sh ensure-ready --project-root {project_root} --open-editor"

# CORRECT (stable for macOS, Linux, and Windows Git Bash)
f"xuunity_light_unity_mcp.sh ensure-ready --project-root {project_root.as_posix()} --open-editor"
```

This applies to recovery commands, `full_payload_command`, `*_recovery_command`,
docs examples generated from code, and any structured payload field whose value
is intended to be pasted into `bash`. Add a regression test with
`PureWindowsPath("C:/tmp/FakeProject")` for helpers that format shell-facing
commands. The test should assert that the command contains `C:/tmp/FakeProject`
and does not contain `\`.

If the durable value will be consumed by native Windows tools instead of Git
Bash, follow rule 7 and persist a host-native path explicitly. Make the target
consumer obvious in the function name or test.

## 9. Never Compare Full Path Strings in Tests

MSYS `/tmp/...`, `C:\Users\RUNNER~1\...` (8.3 short name), and `C:/Users/runneradmin/...` can all be the same directory. Compare separator-normalized suffixes or resolved `Path` equality.

When testing shell-facing commands, do not merely normalize the assertion with
`.replace("\\", "/")`; that can hide a real command-rendering bug. Normalize
only when the value is not itself intended to be copied into a shell.

## 10. Bound Every Spawned Process in Tests

Use `tests/bash_support.py:run_with_timeout()` instead of bare `subprocess.run` for anything that spawns bash: timeout + process-tree kill (`taskkill /T /F` / `killpg`) + partial stdout/stderr dumped to stderr **at the moment the timeout fires**, plus `skip_if_prior_subprocess_timeout` in `setUp` so one hang does not cascade. `tests/test_bash_spawn_canary.py` runs first in the suite as the end-to-end regression guard.

## 11. Do Not Assume a Home Directory Exists in CI

GitHub Windows runners can execute tests with `HOME`/`USERPROFILE` cleared or
unresolvable. `Path.home()` can raise `RuntimeError("Could not determine home
directory.")`. Code that only builds plans, helper targets, optional client
config review paths, or recovery hints must degrade with a safe fallback instead
of crashing.

Add a regression for this class by clearing `os.environ` and mocking
`Path.home()` to raise `RuntimeError`. Use explicit env overrides in tests when
the exact user config path matters.

## 12. cmd Launcher Flavor Rules (`*.cmd`)

The native Windows launchers (`xuunity_light_unity_mcp.cmd`, `run_installed_or_refresh_xuunity_mcp.cmd`, `templates/run.cmd`) have their own trap set, guarded by `tests/test_cmd_launcher_contract.py`:

- **No `%ERRORLEVEL%` token at all.** Inside parenthesized blocks it expands at parse time, so `exit /b %ERRORLEVEL%` returns 0 forever — every wrapper "succeeded" with no Python installed. Use goto flow with `if errorlevel N` and explicit exit codes.
- **No bare `exit /b` either.** When the top-level batch under `cmd /c` terminates via `exit /b` with no code, cmd.exe's *process* exit code is 0 regardless of ERRORLEVEL — the first live Windows e2e run caught ensure-ready failing correctly while the wrapper reported success. Either pass an explicit code (`exit /b 9009`), or make the delegated command the final executed line so the script ends naturally and its ERRORLEVEL becomes the process exit code (subroutines go above the run block).
- **Gate every interpreter candidate through a probe**, not `where python`: the Microsoft-Store WindowsApps stub is found first on fresh machines and cannot run scripts (exit 9009). Probe with `-c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 2)"` before trusting a candidate.
- **Tolerate a quoted `PYTHON` override**: strip quotes (`set "X=%PYTHON:"=%"`) before use — a quoted value inside an `if` block otherwise breaks batch parsing.
- **Default `PYTHONUTF8=1`** (`if not defined PYTHONUTF8 ...`) in every flavor.
- **CRLF end to end** — enforced by `.gitattributes` and the contract test; after editing a `.cmd` from a POSIX host, re-normalize (`perl -pi -e 's/\r?\n/\r\n/'`).
- Keep `.cmd` flavors as thin as the `.sh` ones (rule 6); behavior lives in Python.

## 13. Windows Client-Config argv Entries Must Be Quote-Free

MCP clients (Node libuv, Python `list2cmdline`) quote argv with the C-runtime
rules: an arg containing spaces or quotes gets wrapped, and embedded quotes
become `\"`. cmd.exe does not understand `\"`, so a persisted config arg like
`if defined X (call "%X%\run.cmd") else (call "...")` can never spawn — the
first live config-to-connection e2e caught it as
`'\"C:\...\run_installed_or_refresh_xuunity_mcp.cmd\"' is not recognized`.
Persist the install-time-resolved launcher path as its own argv entry:

```json
"command": "cmd.exe",
"args": ["/d", "/c", "call", "C:\\Users\\me\\.claude-tools\\xuunity-mcp\\run_installed_or_refresh_xuunity_mcp.cmd"]
```

Never embed quotes, parentheses, or env-var conditionals in a Windows
client-config arg (an unquoted `%VAR%` also breaks on expansion when the
value contains spaces). POSIX configs should persist an absolute Bash path,
use `-c` instead of `-lc`, and invoke the launcher through that same shell;
GUI clients may not inherit a developer `PATH`, and login profiles can mutate
the runtime unexpectedly. Guarded by `tests/test_posix_client_config_contract.py`,
`tests/test_windows_client_config_contract.py`, and the config-to-connection
e2e in `tests/test_installed_delegate_e2e.py`.

---

## Bisecting a Hang That Only Reproduces in CI

Spend the first CI round-trip on instrumentation, not on plausible fixes — serial theory-driven fixes cost one round-trip each:

1. **Layer canaries**: minimal tests per spawn layer (bash -c → script file → script + args → script + suspect env → real artifact), short timeouts, run first. The first failing canary names the broken layer.
2. **Prefix ladder**: run growing prefixes of the suspect script (cut at top-level boundaries) with short timeouts; the resulting map (`153=ok 181=TIMEOUT`) brackets the failing line.
3. Read partial output dumped at kill time; zero output from a script that spawns fine means a subshell `$(...)` is spinning, not a launch failure.
4. After the root cause lands, delete the bisection scaffolding and keep one end-to-end canary.
