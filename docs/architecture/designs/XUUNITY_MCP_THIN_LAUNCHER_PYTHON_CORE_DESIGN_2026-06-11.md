# XUUnity MCP: Thin Launchers + Python Core Orchestration

**Date:** `2026-06-11`
**Status:** `Implemented; Phase 4 cleanup complete`
**Driver:** Windows CI silent-hang incident (June 2026) — root cause and every secondary defect lived in the bash layer.

---

## 1. Context & Problem Statement

The repo currently carries ~2,450 lines of operator-side bash:

| Entrypoint | Lines | Role |
| --- | --- | --- |
| `xuunity_light_unity_mcp.sh` | 962 | wrapper: source/install/repo/python resolution, helper sync, devmode/prodmode, compact summaries, dispatch to `server.py` |
| `scripts/testing/run_multi_project_batch_compile_matrix.sh` | 482 | multi-project batch orchestration (`xargs -P`) |
| `scripts/testing/run_multi_project_gui_test_subset.sh` | 1003 | multi-project GUI orchestration (`xargs -P`) |
| `templates/run.sh` / `run.cmd` / `run.ps1` | 54 / 42 / 48 | installed client launchers: find python → exec `server.py` |

### The Problems
1. **Bash is the proven defect surface.** Every defect in the June 2026 incident (non-terminating `dirname` walk, WSL bash resolution, `xargs -P` msys hangs, CRLF sensitivity, backslash env paths) lived in the three large bash files. MSYS emulation makes this a *permanent* risk class — guards cover known traps, not the class.
2. **Windows lost parallelism.** The msys-safe fix replaced `xargs -P` with a sequential loop on Windows: correct but slow for multi-project operators.
3. **`run.cmd` / `run.ps1` are shipped but never executed by CI.** They are the entrypoints Windows MCP clients actually use (see `docs/clients/`), yet only the bash path is tested. Notably, they already embody the target pattern: ~45 lines, find python, exec `server.py`, zero business logic — Windows clients already bypass bash entirely and were unaffected by the incident.
4. **Logic duplication across languages.** Install-dir resolution exists twice (bash `resolve_neutral_install_dir` and Python `server_setup_wizard.get_neutral_install_dir`), drifting independently.

### Insight
The cross-platform-safe implementation of nearly everything the wrapper does **already exists in Python** under `templates/` and is exercised by 221 tests on three OSes in CI. The bash layer is not adding capability; it is re-implementing capability in the least testable language on the most fragile platform.

---

## 2. Goals

1. Every shell entrypoint (`.sh`, `.cmd`, `.ps1`) becomes a **thin launcher ≤ 30 lines**: locate a Python ≥ 3.10 interpreter, exec the Python core, forward args and exit code. Nothing else.
2. All wrapper logic moves to a Python module; all multi-project orchestration moves to a Python module with **real cross-platform parallelism**.
3. `xargs` disappears from the repo; Windows regains `--parallelism N`.
4. CI executes all three launcher flavors on the Windows leg.
5. CLI surface is preserved exactly: command names, env-var contract (`XUUNITY_LIGHT_UNITY_MCP_*`, `PYTHON`), and the stdout line contract tests assert on (`package_source=`, `verdict=`, `MULTI_PROJECT_*_SUMMARY_BEGIN`, status JSON files).

### Non-Goals
- No changes to the MCP protocol, `server.py` tool surface, or the Unity package.
- No new CLI commands; behavior-preserving port only.
- Client setup docs change only where entrypoint invocation changes (target: no change).

---

## 3. Design

### 3.1 Phase 0 — CI gate first (independent, do immediately)
- Add `push: branches: [master]` and `pull_request` triggers to the offline-checks job (it now completes in ~1–2 min per leg).
- Add two Windows smoke steps: invoke `templates/run.cmd` and `templates/run.ps1` with `--help` against the source tree and assert exit 0 + usage output. This closes the untested-entrypoint gap *before* the port and gives the port a parity baseline.

### 3.2 Phase 1 — Wrapper core in Python
New module `templates/server_launcher.py` (stdlib only, same import discipline as other `server_*.py` modules), owning in order of port:
1. `resolve_source_root`, `resolve_repo_root` — `Path.resolve()` walks with natural fixed-point termination; dedupe with existing helpers.
2. `resolve_install_dir` — delegate to the existing `server_setup_wizard` resolution (kills the bash/python duplicate).
3. Helper sync (`sync_installed_helper_if_needed`) — `shutil` + content compare.
4. Compact summary emission — today a python heredoc inside bash; becomes a plain function (removes a whole escaping layer).
5. `devmode` / `prodmode` — git operations via `subprocess.run(["git", ...])`; tag/remote checks ported 1:1.
6. Dispatch: forwards server commands to `server.py` in-process (import) or via `exec` semantics (`os.execv` on POSIX, `subprocess` + exit-code passthrough on Windows).

`xuunity_light_unity_mcp.sh` shrinks to: find python (the only resolve that cannot live in Python — bootstrap chicken-and-egg, ~12 lines, ported from the already-thin `run.sh` pattern) → `exec "$PYTHON_BIN" templates/server_launcher.py "$@"`. New sibling `xuunity_light_unity_mcp.cmd` and `.ps1` with identical contract.

### 3.3 Phase 2 — Orchestration in Python with real parallelism
New `scripts/testing/run_multi_project.py` (single module, two subcommands: `batch-compile-matrix`, `gui-test-subset`):
- Worker = one wrapper subprocess per project, executed via `concurrent.futures.ThreadPoolExecutor(max_workers=parallelism)`. Workers are I/O-bound subprocess waits, so threads are correct and the GIL is irrelevant; **no fork, no msys emulation involved — identical parallel behavior on all three OSes.**
- Per-worker timeout + process-tree kill: promote `run_with_timeout`/`_kill_process_tree` from `tests/bash_support.py` into a small shared util consumed by both the orchestrator and the tests.
- Status JSON, aggregate summary, verdict classification: port the existing python heredocs as plain functions; the file/stdout contract stays byte-compatible where tests assert it.
- The two `.sh` runner scripts become 5-line shims (`exec python run_multi_project.py batch-compile-matrix "$@"`) for one release, then are removed.

### 3.4 Phase 3 — Tests
- Existing 221 tests keep passing unchanged (they call entrypoints by path and assert the output contract — that is the point of preserving it).
- New parity test on the Windows leg: same `--help` and one representative command through `.sh`, `.cmd`, `.ps1` → identical stdout contract.
- New parallelism test: 3 fake projects, `--parallelism 3`, assert overlapping execution (worker start/end timestamps in status files) — must pass on the Windows leg.
- The bash-spawn canary stays as the regression guard for the launcher layer.

### 3.5 Phase 4 — Cleanup & release
- Delete dead bash, update `CHANGELOG.md`, version bump, refresh `docs/agents/` + `docs/operations/` references, re-run release-versioning consistency tests.

Phase 4 closeout note, 2026-06-11:

- `v0.3.27` provided green Windows, macOS, and Linux evidence for the Python
  launcher core.
- `xuunity_light_unity_mcp_legacy.sh` and the
  `XUUNITY_LIGHT_UNITY_MCP_LEGACY_WRAPPER` escape hatch were removed after that
  evidence.
- The golden dual-run parity suite was retired with its legacy subject.
- Cross-flavor launcher parity, bash-spawn canary coverage, and the regular
  contract suite remain as regression guards.

---

## 4. Porting Safety (the main risk)

A 962-line behavioral port is the risk center. Mitigations, in priority order:
1. **Golden-output baseline before the port**: record current wrapper stdout/exit codes for every command exercised by tests, on all three CI legs, into versioned fixtures. The port must reproduce them.
2. **Command-by-command port**: each command moves in its own commit with its golden test; the bash implementation stays callable (env flag `XUUNITY_LIGHT_UNITY_MCP_LEGACY_WRAPPER=1`) until the full surface is proven, then the flag and dead code are removed in Phase 4. This cleanup was completed after the `v0.3.27` cross-platform evidence.
3. **No semantic improvements during the port.** Behavior changes (if any are discovered as desirable) are filed as follow-ups; the port itself is mechanical.

Residual risks to state honestly: `py -3` launcher quoting on Windows, `os.execv` signal semantics on POSIX vs subprocess passthrough on Windows, and git output parsing differences — each is covered by an existing or new test, but real-Unity flows remain validated only as far as current CI exercises them.

---

## 5. Success Criteria

- [x] Each shell entrypoint ≤ 30 lines; no resolves, loops, or business logic in shell.
- [x] `grep -r xargs` over the repo returns nothing.
- [x] `--parallelism 3` demonstrably overlaps workers on the Windows CI leg.
- [x] `.sh`, `.cmd`, `.ps1` all executed green in CI on Windows.
- [x] Offline checks run on push/PR, not only on tags.
- [x] Full suite green on macOS, Ubuntu, Windows; legacy golden parity retired after the Python core was proven.

## 6. Sequencing & Effort

| Phase | Scope | Relative effort | Can ship alone |
| --- | --- | --- | --- |
| 0 | CI triggers + cmd/ps1 smoke | XS | yes — do first |
| 1 | Wrapper → `server_launcher.py` | L (dominated by golden tests) | yes, behind legacy flag |
| 2 | Runners → `run_multi_project.py` | M | yes |
| 3 | Parity + parallelism tests | S | with 1–2 |
| 4 | Cleanup, version, docs | S | last |
