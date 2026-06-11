---
name: cross-platform-shell
description: Rules for bash scripts, wrappers, and CI steps in this repo that must run identically on macOS, Linux, and Windows Git Bash (MSYS), plus the bisection workflow for hangs that reproduce only in CI.
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

## 8. Never Compare Full Path Strings in Tests

MSYS `/tmp/...`, `C:\Users\RUNNER~1\...` (8.3 short name), and `C:/Users/runneradmin/...` can all be the same directory. Compare separator-normalized suffixes or resolved `Path` equality.

## 9. Bound Every Spawned Process in Tests

Use `tests/bash_support.py:run_with_timeout()` instead of bare `subprocess.run` for anything that spawns bash: timeout + process-tree kill (`taskkill /T /F` / `killpg`) + partial stdout/stderr dumped to stderr **at the moment the timeout fires**, plus `skip_if_prior_subprocess_timeout` in `setUp` so one hang does not cascade. `tests/test_bash_spawn_canary.py` runs first in the suite as the end-to-end regression guard.

---

## Bisecting a Hang That Only Reproduces in CI

Spend the first CI round-trip on instrumentation, not on plausible fixes — serial theory-driven fixes cost one round-trip each:

1. **Layer canaries**: minimal tests per spawn layer (bash -c → script file → script + args → script + suspect env → real artifact), short timeouts, run first. The first failing canary names the broken layer.
2. **Prefix ladder**: run growing prefixes of the suspect script (cut at top-level boundaries) with short timeouts; the resulting map (`153=ok 181=TIMEOUT`) brackets the failing line.
3. Read partial output dumped at kill time; zero output from a script that spawns fine means a subshell `$(...)` is spinning, not a launch failure.
4. After the root cause lands, delete the bisection scaffolding and keep one end-to-end canary.
