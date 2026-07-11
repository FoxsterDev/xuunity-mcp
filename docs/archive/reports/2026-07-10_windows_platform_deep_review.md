# XUUnity Light Unity MCP — Windows Platform Deep Review

Date: 2026-07-10 (implementation status updated 2026-07-11)
Status: review complete; Waves 1–3 implemented on `master` (unreleased); Wave 3 item 12 (live colleague-host session) remains the only open item
Scope: why colleagues on plain Windows machines cannot set up and use the MCP that works flawlessly on macOS
Source reviewed: this repo @ `e49334e` (post-v0.3.42)
Method: 4 parallel audit lanes (retro/fix history, install surface, server templates, CI coverage) + manual review of the Unity C# bridge and repo routers. All `file:line` refs are relative to the MCP repo root.

---

## TL;DR

macOS works because it has exactly one code path (bash → python3 → POSIX) that the maintainer exercises live every day. Windows has four shell layers (cmd / PowerShell / Git Bash / WSL) × three launcher flavors × the Microsoft-Store Python stub — and **the end-to-end Windows path has never been executed successfully as a whole, by anyone, anywhere**: not in CI (offline checks only, no Unity, no MCP stdio round-trip), not on a real machine (`docs/reference/STATUS.md:207` says it plainly: *"native Windows MCP connection still needs host execution proof"*).

Twelve Windows failure classes were documented across five retros (2026-06-09 → 2026-07-06). Every retro got a same-day fix commit, but every fix was validated only by unit tests / offline CI — **zero fixes were ever re-verified on a real Windows machine**. Meanwhile four systemic P0 defects remain in current source that break a fresh Windows setup at the very first step, before any of the previously-fixed classes are even reached.

The four walls a fresh-Windows colleague hits, in order:

1. **First `.cmd` invocation silently "succeeds" with no Python.** All three `.cmd` wrappers have a parse-time `exit /b %ERRORLEVEL%` bug → they always exit 0; on a fresh box `where python` finds the Microsoft-Store stub, which fails, and the wrapper still reports success. No actionable error is ever shown.
2. **Git Bash is secretly mandatory.** The only installer is a bash script; every Windows client config template points at delegate `.cmd` files that only that bash installer creates; the refresh launcher shells out to Git Bash at every client start; and the native sync never installs `run.cmd`, so the bash path re-triggers forever.
3. **Russian locale kills the server.** The MCP stdio loop decodes stdin with the ANSI codepage — a Cyrillic character in `projectRoot` crashes or mojibakes the server; CLI output with `ensure_ascii=False` raises `UnicodeEncodeError` on cp866 consoles; PowerShell/tasklist output is decoded with the wrong codepage, breaking editor detection on RU Windows.
4. **Unity on any drive other than `%ProgramFiles%` is undiscoverable**, and the documented env-var escape hatch does not work because the Windows glob set lacks a `*/Editor/Unity.exe` pattern.

Even past those walls, the documented first-run sequence still dead-waits the full 120 s (`ensure-ready` heartbeat wait with the package declared but not yet resolved — the 2026-06-17 retro class, only half-fixed), and every recovery command the tool prints is a POSIX-shaped, unquoted `.sh` command that reproduces the historical path-truncation failure when pasted on Windows.

---

## 1. The fresh-Windows funnel and where it breaks

Documented shortest path: README "Native Windows quickstart from cmd.exe" (`README.md:237-247`, mirrored `INSTALL.md:192-201`) → clone, run `xuunity_light_unity_mcp.cmd setup-plan / setup-apply / validate-setup / ensure-ready`, copy a `templates/clients/*/*.windows.json`.

| Step | What happens on a fresh Windows machine | Break |
| --- | --- | --- |
| 0. Prerequisites | `README.md:82-85` checks Python via `command -v python3` — bash syntax; fails in cmd/PowerShell before anything starts | doc |
| 1. `xuunity_light_unity_mcp.cmd setup-plan` | `where python` → WindowsApps Store stub → stub prints Microsoft's Store message and exits 9009 → **wrapper exits 0 anyway** (parse-time `%ERRORLEVEL%`); `%TEMP%\xuunity-setup-plan.json` is empty; agent/CI sees success | **P0-1** |
| 1b. Same step pasted into PowerShell (what most users actually do) | bare `xuunity_light_unity_mcp.cmd` (no `.\`) and `%TEMP%` both fail — the quickstart block says "from cmd.exe" but shows no PS variant | doc |
| 2. Install real Python, retry | setup-plan/apply/validate now work natively | — |
| 3. `ensure-ready --open-editor` | bridge config was already enabled by setup-apply → the only fast-fail (`bridge_disabled`) is disarmed → full 120 s heartbeat wait while Unity resolves the Git-UPM package; **`git.exe` absent on a fresh machine → package can never resolve** → `editor_ready_timeout` with a bash-flavored, unquoted recovery hint | **P0/P1** |
| 4. Wire the MCP client | copied `.windows.json` points at `%USERPROFILE%\.claude-tools\...\run_installed_or_refresh_xuunity_mcp.cmd` — **created only by the bash installer** → must install Git for Windows and run `init_xuunity_light_unity_mcp.sh` anyway | **P0-2** |
| 5. Every client start thereafter | refresh launcher requires Git Bash (`run_installed_or_refresh_xuunity_mcp.py:102-123`) and re-triggers the bash installer whenever `run.cmd` is missing from the neutral dir — which it always is, because `server_launcher.py` sync never installs it (`server_launcher.py:32,412` vs trigger at `run_installed_or_refresh_xuunity_mcp.py:131,172`) | **P0-2** |
| 6. Any Cyrillic path / RU console | stdio ANSI decode kills the server; `print_json(ensure_ascii=False)` raises on cp866 console | **P0-3** |
| 7. Unity installed on D: | discovery scans only `%ProgramFiles%*`; `XUUNITY_UNITY_EDITOR_ROOTS` glob set can't match a Hub editor root | **P0-4** |

---

## 2. P0 — blocks setup on a plain Windows machine

### P0-1. All `.cmd` wrappers always exit 0 + Microsoft-Store stub swallow
- Parse-time `exit /b %ERRORLEVEL%` inside parenthesized `if` blocks — expanded when the block is parsed, not when it runs: `xuunity_light_unity_mcp.cmd:13,19,25,31`; `run_installed_or_refresh_xuunity_mcp.cmd:12,17,23,29,35`; `templates/run.cmd:15,20,26,32,38`. Result: **setup failures return exit code 0** to agents, scripts, and CI.
- On a fresh box `where python` finds `%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe` (Store alias); it fails with Microsoft's Store message, and thanks to the bug above the wrapper still "succeeds". The wrappers' own friendly "install Python" message is unreachable (`xuunity_light_unity_mcp.cmd:22-34`).
- `.cmd` flavors have **no Python ≥3.10 gate** (only `templates/run.sh:48-52` and `server_launcher.py:22-28` do).
- Bonus trap: `set PYTHON="C:\Program Files\...\python.exe"` (the natural copy-paste form, with quotes) breaks block parsing in all three `.cmd` files (`xuunity_light_unity_mcp.cmd:8,11` et al.).

Fix: `exit /b` without an argument (or delayed expansion); detect the WindowsApps stub explicitly (e.g. reject interpreters under `\Microsoft\WindowsApps\`); mirror the version probe into `.cmd`; tolerate quoted `PYTHON`.

### P0-2. Circular Git-Bash dependency — the Windows install is not self-hosting
- The **only installer is bash** (`init_xuunity_light_unity_mcp.sh`); every install doc step is `bash init_...` (`README.md:492-493`, `INSTALL.md:150-152`, `docs/clients/claude-code.md:10-12`, `cursor.md:13`, `claude-desktop.md:10-12`, `codex.md:61-63`) — directly contradicting the repo's own "Git Bash is not the recommended native Windows route" (`README.md:249-252`, `INSTALL.md:203-206`).
- All Windows client templates point at `%USERPROFILE%\.claude-tools\...` / `.codex-tools\...` delegate `.cmd` files that **only the bash installer writes** (heredocs at `init_xuunity_light_unity_mcp.sh:559-666`).
- `--install-claude-config` writes a `"command": "bash", "args": ["-lc", ...]` block **unconditionally** (`init_xuunity_light_unity_mcp.sh:379-384`) — the Codex path has a proper `is_windows_like_host` → `cmd.exe` branch plus a `windows_codex_launcher_mismatch` warning (`:302-322`); the Claude path got neither. On a bashless Windows machine the Claude Code server entry can never start.
- Runtime re-entry: `run_installed_or_refresh_xuunity_mcp.py` hard-requires Git Bash on `nt` (`:102-123`) and re-runs the bash installer whenever the installed version mismatches **or `run.cmd` is missing** (`:131`) — and `run.cmd` is always missing because `server_launcher.py`'s sync installs `run.sh` only (`server_launcher.py:32,412-418,439`). Two independent Git-Bash traps.
- Generated delegates use `os.execv` unconditionally (`init...sh:590-597,637-657`): on Windows exec spawns a child and kills the parent — an MCP client watching its direct child sees the server die. (The maintained launchers handle `nt` correctly via `subprocess.run` — `run_installed_or_refresh_xuunity_mcp.py:150-159`, `server_launcher.py:370-377`; the heredoc-generated delegates do not.)
- The bash-re-entry path itself is fragile: refresh passes a backslash Windows script path into `bash <script>`; `dirname "$0"` inside init (`:88`) doesn't split backslash paths → `script_dir` degrades to `.` → copy steps fail from an arbitrary cwd. This matches the recurring "install keeps failing the same way" memory.

Fix direction: make Windows self-hosting — a native installer path (`.cmd`/`py`), Windows branch for `--install-claude-config`, ship delegates as CRLF template files instead of heredocs, `subprocess` instead of `execv` in delegates, sync `run.cmd`/`run.ps1` in `server_launcher.py`, and make the refresh fall back to the native `.py` route instead of failing without Git Bash.

### P0-3. Encoding/locale: RU Windows (cp1251/cp866, Cyrillic paths) is unsupported
- **MCP stdio**: `serve_stdio` iterates `for raw_line in sys.stdin` (`templates/server_mcp_protocol.py:145`) — decode happens in the `for` statement, outside try/except, with the ANSI codepage on Windows. A UTF-8 Cyrillic byte sequence in any request (e.g. `projectRoot: C:\Users\Иван\...`) → `UnicodeDecodeError` → **server process dies**; milder cases mojibake the path → `project_not_found`. No `reconfigure`/`PYTHONUTF8`/`PYTHONIOENCODING` anywhere in the tree (verified by sweep).
- **CLI output**: the single shared `print_json` uses `ensure_ascii=False` (`templates/server_batch_orchestrator.py:2404-2405`) → `UnicodeEncodeError` on cp866/cp1251 consoles for any non-ASCII payload; redirected output (`> "%TEMP%\...json"`, README:241) is written in ANSI, which `read_json` (UTF-8/UTF-16 only, `templates/server_core.py:17-45`) then refuses in `setup-apply`. (The MCP wire itself is safe — `emit_message` is `ensure_ascii=True`, `server_mcp_protocol.py:39`.)
- **Process listing**: PowerShell/tasklist output parsed with `text=True` and no `encoding` (`templates/server_host_platform.py:80-88,104-113,149-155`); PS 5.1 emits OEM (cp866 on RU) while Python decodes ANSI (cp1251) → Cyrillic command lines mojibake → `unity_command_targets_project` never matches → editor reuse/close detection breaks; undefined bytes raise `UnicodeDecodeError` that escapes the `except OSError` and crashes the tool.
- **Manifest edits**: `read_text()`/`write_text()` without encoding in devmode/prodmode flows (`templates/server_launcher.py:524-538`).

Fix: `sys.stdin/stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` at server start; set `PYTHONUTF8=1` in all launchers and client config templates; `[Console]::OutputEncoding=UTF8` prefix + `encoding="utf-8", errors="replace"` on every subprocess; `encoding="utf-8"` on every `open/read_text/write_text`.

### P0-4. Unity editor discovery ignores non-default install locations
- Native-Windows candidate roots = `ProgramFiles`/`ProgramW6432`/`ProgramFiles(x86)` only (`templates/server_editor_host_discovery.py:199-210`). No Unity Hub `secondaryInstallPath.json` (`%APPDATA%\UnityHub\`), no registry, no other drives — ironically the WSL branch does scan `/mnt/c,d,e` (`:212-219`).
- The documented escape hatch is broken for natural values: the Windows glob set (`:248-261`) lacks `*/Editor/Unity.exe`, so `XUUNITY_UNITY_EDITOR_ROOTS=D:\UnityEditors` (or even the exact Hub editors root) discovers nothing; the error then tells the user to set exactly that env var (`templates/server_editor_host_paths.py:96-105`).
- Anyone who moved Hub's "Installs location" off C: — common on dev machines with small system SSDs — is hard-blocked.

Fix: add `*/Editor/Unity.exe` glob; read Hub's `secondaryInstallPath.json` + `editors-v2.json`; include the searched roots in the error payload.

---

## 3. P1 — breaks common flows even after setup

1. **`ensure-ready` first-open dead-wait is still the designed behavior** (retro class (c), half-fixed). Import state is computed before waiting but never branched on (`templates/server_cli_commands.py:440-448`); `wait_for_ready` fast-fails only on `bridge_disabled` (`server_editor_host_lifecycle.py:786-795`) — and the documented sequence disarms that by enabling bridge config in setup-apply (`server_setup_apply.py:33-34,104-105`). Post-timeout diagnosis covers `declared_not_resolved`/`resolved_not_cached` (`server_cli_commands.py:516-528`, `server_cli_bridge_commands.py:775-791`) but **not `not_declared`** — a fresh machine that skipped setup-apply waits the full 120 s (`server_cli_parser.py:491`) for a generic `editor_ready_timeout`. First open additionally requires `git.exe` for the Git-UPM URL — absent on fresh Windows, undiagnosed.
2. **Every printed recovery command is `.sh`-flavored, POSIX-shaped, and unquoted**: `templates/server_readiness_summary.py:105,139,172-173,181-182,191`; `server_cli_commands.py:526`; `server_cli_bridge_commands.py:788-790`; `server_editor_host_lifecycle.py:538,790-793`; `server_bridge_transport.py:561`; `server_setup_plan.py:181,192`; also init's next-steps (`init...sh:728-733`, `python3` + unquoted spaced path). An agent pasting these on Windows re-triggers the historical `D:\Unity Projects\Foo` → `D:\Unity` truncation. Commit `81f4f29` ("Fix Windows recovery command paths") normalized path rendering but kept the `.sh` flavor and unquoted interpolation. `launcher_display_name()` already exists (`server_launcher.py:52-53`) — recovery templates just don't use it.
3. **Stale-PID force-kill without identity re-check** (residual of the 2026-06-10 kill catastrophe): `restore_host_opened_editor_state` taskkills `managed_pid` from the persisted session file guarded only by generic liveness (`server_editor_host_lifecycle.py:588-591,684`; `terminate_editor_pid` at `:415-425`; `pid_is_alive` checks any process, `server_host_platform.py:40-73`). If Windows recycled the pid to another app while live editors exist, that app is killed; the membership check runs after the kill (`:685-686`).
4. **File-IPC not crash-safe on Windows.** Python `write_json` writes final paths directly, no temp+`os.replace` (`templates/server_core.py:53-57`; used for inbox at `server_bridge_transport.py:124`). Response read has no error handling and the `finally` unlinks the response — a partial-write `JSONDecodeError` or AV-induced `PermissionError` crashes the call **and destroys the response** (`server_bridge_transport.py:142-150`). C# side mirrors this: `File.WriteAllText` direct writes for `bridge_state.json` (the heartbeat file Python polls; `Editor/Bridge/XUUnityLightMcpBridgeStateWriter.cs:103`) and outbox responses (`Editor/Core/XUUnityLightMcpResponseWriter.cs:49`). TCP loopback (primary transport) masks this for responses, but file mode is the fallback and bridge-state polling is always file-based.
5. **devmode/prodmode**: `os.path.relpath` raises unhandled `ValueError` when project and MCP repo live on different drives (`templates/server_launcher.py:549-552`); `file:` dependencies rendered with backslashes on Windows (`server_launcher.py:549-552`, `server_setup_plan.py:123-127`) — UPM's documented `file:` form is forward-slash.
6. **Launcher-flavor divergence**: interpreter order `.sh` = python3→python→py vs `.cmd`/`.ps1` = py→python→python3 (in Git Bash on Windows, `.sh` picks the Store stub even when a real `py` exists); venv precedence inverted between `templates/run.sh:23-36` (venv > `$PYTHON`) and `run.cmd:9-21`/`run.ps1:9-27` (`$PYTHON` > venv) — the README "set PYTHON" advice behaves oppositely per platform; version gate exists only in `run.sh`; only one flavor of the refresh pair checks the venv.
7. **Docs steer Windows users into bash**: prerequisites (`README.md:82-85`), the entire Agent Quick Start + copy-paste "AI Agent Setup Prompt" (`README.md:223-235,360-446`) — an AI assistant on a Windows host following the README verbatim runs bash commands; repo router `Agents.md` lists only `.sh` files as "Public shell entrypoints"; verify/uninstall/smoke flows are bash+`/tmp` in all client docs; `docs/clients/codex.md` is the only near-complete Windows story.

---

## 4. P2 — papercuts and latent hazards

1. No `timeout=` on any subprocess call (tasklist/PowerShell/taskkill/lsof/git) — a hung WMI freezes every status/ensure-ready call (`server_host_platform.py:80-155`, `server_editor_host_lifecycle.py:425,446`, `server_editor_host_processes.py:268-273`, `server_launcher.py:474-491`).
2. No `CREATE_NO_WINDOW` on helper spawns — console flashes from 0.2 s polling loops under GUI-hosted clients (only the Unity launch itself sets creationflags, `server_editor_host_lifecycle.py:291-299`).
3. Windows lock-owner detection is an lsof-only stub → `Temp/UnityLockfile` ownership always reports zero owners; `project_already_open_without_bridge` branch unreachable on Windows (`server_editor_host_processes.py:259-317`, `lifecycle:185-195`).
4. `taskkill` without `/T` — import workers can survive and hold the project lock (`lifecycle:425,446`).
5. No raw-argv echo on argparse failure (`templates/server.py:237-242`) — the historical truncation class remains undiagnosable at the failure point (the Git-Bash hint on `project_not_found`, `server_project_context.py:29-44`, is good but downstream).
6. Version-mismatch silent fallback to the newest installed Unity → interactive upgrade dialog → guaranteed ensure-ready timeout that looks like a bridge failure (`server_editor_host_paths.py:125-135`).
7. Long paths: no `\\?\` handling; deep `Library/PackageCache` globs silently miss without LongPathsEnabled → wrong `resolved_not_cached` classification (`server_project_context.py:189-201`).
8. C# `TcpListener` sets `SO_REUSEADDR` before bind (`Editor/Bridge/XUUnityLightMcpBridgeTransportRuntime.cs:270`) — harmless with the default ephemeral port (`loopback_port: 0`, `server_setup_apply.py:44`), but on Windows a user-pinned port could be silently double-bound by a second editor (`SO_EXCLUSIVEADDRUSE` is the Windows-correct flag).
9. Heredoc-generated delegate `.cmd` files are LF-only with mixed separators (`init...sh:605-631`) — parses today, known cmd.exe edge.
10. `docs/clients/claude-code.md:108-109` `claude mcp add` one-liner uses `""..""` escaping in a PowerShell fence — mangled under PS 5.1 / pwsh < 7.3 argument passing.
11. `.ps1` wrappers carry no ExecutionPolicy guidance in-file; `$MyInvocation`-based dir resolution breaks under `-Command` invocation (`xuunity_light_unity_mcp.ps1:1-6`).

---

## 5. The meta-problem: the fix loop never closes on a real Windows machine

- **History**: 12 distinct failure classes over five retros (2026-06-09 v1/v2, 2026-06-10 kill catastrophe, 2026-06-17 setup failure, plus the macOS 2026-07-06 bridge-enable retro). Every retro produced a same-day/next-day fix commit (`c7d096d`, `0c95d84`, `3297e85`, `b0ea846`). **None** of the retros or the registry claims post-fix verification on real Windows; the 2026-06-17 retro explicitly defers "native Windows repro" and "live Windows Unity validation" — still open today.
- **CI** (`.github/workflows/windows-integration-tests.yml`): one `offline-ci` job, Python 3.11, no Unity. What it does *not* exercise: the documented README flow (CI calls `python templates/server.py` under bash, not the `.cmd` quickstart); `setup-apply`/`ensure-ready` through any wrapper; **the MCP stdio loop — `serve_stdio` has zero test references on any OS**; `.ps1` under default ExecutionPolicy (parity test passes `-ExecutionPolicy Bypass`; workflow uses GH `pwsh`); MSYS path conversion (the parity test deliberately sets a native env dir to *avoid* conversion, `tests/test_launcher_flavor_parity.py:48-53`); non-ASCII/Cyrillic anything; real process kills. Consequence: ≥6 "fix Windows CI" repair commits post-merge (`20c3004`, `81f4f29`, `a8f0906`, `63c3b40`, `83bd046`, `d4ae01e`) — breakage is discovered downstream, never prevented.
- **The `.cmd` exit-0 bug makes CI complicit**: the workflow's `.cmd` smoke steps grep stdout for "usage:" (good), but any scenario relying on exit codes passes vacuously.
- **Honest self-assessment already exists**: `docs/reference/STATUS.md:207` ("templates provided … still needs host execution proof"), `STATUS.md:306`, `ROADMAP.md:197-210` (Windows claims "should remain conservative until executed on those hosts"). The gap is not awareness — it is that no workflow forces the proof before colleagues are pointed at the tool.

---

## 5b. Wave 1 implementation status (2026-07-11, MCP repo `master`)

| Item | Status | Commit |
| --- | --- | --- |
| W1-1 `.cmd` correctness (exit /b parse bug, Store-stub rejection, 3.10 gate, quoted PYTHON) | done + tests (`tests/test_cmd_launcher_contract.py`) | `61f77ad` |
| W1-2 UTF-8 host-wide (stdio reconfigure, PYTHONUTF8 in all launchers, subprocess/file encodings, PS OutputEncoding, forward-slash `file:` deps + cross-drive fallback) | done + tests (`tests/test_windows_encoding_contract.py`) | `443727c` |
| W1-3 Unity discovery (Hub `secondaryInstallPath.json`, direct `*/Editor/Unity.exe` globs, searched-roots in `unity_app_not_found`) | done + tests | `8bd6267` |
| W1-4 ensure-ready fail-fast (`package_not_declared`, `git_executable_missing_for_package_resolve`, 300 s first-import extension) | done + tests | `539104b` |
| W1-5 recovery commands (host-matched launcher flavor via `render_launcher_cli`, quoted paths, `{launcher}` templates) | done + tests | `d83080d` |
| W1-6 self-hosting Windows install (Claude config Windows branch w/ mismatch replacement, run.cmd/run.ps1 in native sync, CRLF delegates, subprocess-not-execv delegates, refresh native-first fallback) | done + tests | `575dea1` |

Wave 1 complete: full suite 339/339 green (4 native-Windows tests skip on macOS and run on the Windows CI leg). Remaining intentional gaps: `init_...sh --enable-project` advisory strings still name the bash installer (accurate — bash install path still exists; the refresh hot path no longer needs it); docs pass (PowerShell-first quickstart, Agents.md entrypoints) deferred to Wave 3 item 13.

## 5c. Wave 2 implementation status (2026-07-11, MCP repo `master`)

| Item | Status | Commit |
| --- | --- | --- |
| W2-7 atomic IPC publication both sides (Python `write_json` temp+`os.replace` w/ PermissionError retry + direct-write fallback; C# `XUUnityLightMcpAtomicFileWriter` temp+`File.Replace` behind ALL 13 polled-file writers — bridge_state, outbox, generation/playmode/test-run state, journal, capabilities, batch/scenario results; file-IPC response reader + `try_take_recovered_response` retry-until-deadline, unlink only after successful parse) | done + tests (`tests/test_atomic_ipc_contract.py`: 12 — write_json atomicity/retry/fallback, transport partial-response retention + mid-flight completion, C# single-writer sweep, .meta guid uniqueness) | `e61f575` |
| W2-8 PID identity gate before kill (`restore_host_opened_editor_state` refuses `taskkill /F` on an alive session pid absent from `list_live_project_editor_pids` → new `tracked_pid_not_project_editor` classification, session file preserved; `taskkill` gains `/T`) | done + tests (`tests/test_editor_host_kill_identity.py`: 3 — foreign-pid refusal, visibility-restricted refusal, confirmed-pid kill path) | `e61f575` |
| W2-9 helper subprocess timeouts + `CREATE_NO_WINDOW` (tasklist 10 s, PS/ps listing 30 s w/ new `process_listing_timeout` code — `TimeoutExpired` previously escaped `except OSError`; lsof 10 s, wslpath 10 s, taskkill 15 s, macOS `open` 30 s, launcher git 30/60 s, workspace git 30 s, refresh native 120 s / bash 300 s; `server_core.hidden_window_subprocess_kwargs()` on all Windows-facing spawns) | done + tests (`tests/test_subprocess_timeout_contract.py`: 8 — AST sweep over `templates/*.py` + refresh with explicit no-timeout allowlist for server/batch self-runs, taskkill `/F /T` argv contract, timeout-classification behavior) | `e61f575` |
| Bonus: latent Wave-1 `NameError` fix — `verify_project_editor_closed` used `render_launcher_cli` without an import in the lifecycle module (only reachable when live project editors exist + process visibility available; caught by the new kill-identity test) | done | `e61f575` |

Wave 2 scope notes: suite now 363/363 green (4 skips). New C# file syntax-checked with mono `mcs`; consumer projects pin the released git tag (`v0.3.42`), so local package edits are exercised only at the next release tag or a Wave-3 live session. Deferred from the original Wave-2 list (item 10 + parts of 9): Windows lock-owner probe (lsof-only stub), raw-argv echo on argparse failure, fail-fast `unity_version_mismatch` — folded into Wave 3 follow-ups and implemented there (see §5e).

## 5d. Editor main-thread load review (2026-07-11)

Follow-up review after the Wave-2 C# changes, focused on "the bridge must not lag the editor": everything the bridge does per tick runs on the editor main thread (`EditorApplication.update`), so any blocking call there is a frame stall.

Fixed:

| Finding | Fix |
| --- | --- |
| **Wave-2 regression:** `XUUnityLightMcpAtomicFileWriter` retried `File.Replace` with `Thread.Sleep(20)` ×5 — up to 100 ms main-thread stall whenever the host poller (5 Hz reads during active operations) held `bridge_state.json` at heartbeat time | sleeps removed: 3 immediate attempts, then fall back to the legacy in-place `File.WriteAllText` (the host's retry-until-deadline reader tolerates its torn reads); contract test now forbids `Thread.Sleep` in the writer and package-wide (single allowlisted pre-existing exception below) |
| `WriteHeartbeat` allocated `Process.GetCurrentProcess()` (undisposed handle) every 2 s heartbeat | pid resolved once into a static and reused |
| `TryWriteResponse` (tcp_loopback) wrote the response with a blocking send on the main thread with **no send timeout** — a dead peer with a full send buffer would freeze the editor until the OS TCP timeout | `TcpClient.SendTimeout = 5000` before the write; timeout surfaces as the already-handled IOException path |

Reviewed and acceptable as-is:

- Heartbeat is throttled to 2 s and the pump to 0.5 s (`XUUnityLightMcpBridgeBootstrap.OnUpdate`) — no per-frame work.
- `PumpOnce` per 0.5 s: `EnsureDirectories` + one `DirectoryInfo.GetFiles("*.json")` over a normally-empty inbox — cheap; `LifecycleMonitor.Tick`/`ScenarioRunner.Tick` are field polls with early-outs.
- `XUUnityLightMcpHealthProbe.EnsureCurrentReport` is memory-cached; heartbeat does not re-probe.
- `XUUnityLightMcpTestRunState.TryLoadActive` per heartbeat is `File.Exists`-guarded; it reads/parses the state file only while a test run is actually active.
- TCP `AcceptLoop` runs on a dedicated background thread; request decode happens off the main thread.

Known remaining (documented, allowlisted, on-demand only — not per-tick): `XUUnityLightMcpGameViewUtility` sleeps `Thread.Sleep(100)` twice as a repaint-settling delay during explicitly requested screenshot/game-view operations. Sleeping the main thread cannot advance repaint anyway, so this should become a frame-deferred capture (`EditorApplication.delayCall`/update-driven) in a follow-up; left untouched now to avoid destabilizing screenshot timing.

Suite after this pass: 364/364 green (4 skips).

## 5e. Wave 3 implementation status (2026-07-11, MCP repo `master`)

| Item | Status |
| --- | --- |
| W3-11 e2e stdio smoke (`tests/test_mcp_stdio_e2e.py`: the real launcher process — bash+`.sh` on POSIX, cmd.exe+`.cmd` on Windows — driven through MCP `initialize` → `tools/list` → `tools/call xuunity_setup_plan` → `ping`; first executable coverage of `serve_stdio` on any OS; exit-code propagation through the wrapper chain; Cyrillic+spaces project-path round-trip with the ASCII-frame contract; protocol errors survive the session; `ensure-ready --open-editor` with `XUUNITY_UNITY_EDITOR_ROOTS` at an empty dir fails in seconds with `unity_app_not_found` + searched roots instead of the 120 s wait) | done + tests (5) |
| W3-11b `.ps1` under stock ExecutionPolicy (`tests/test_ps1_execution_policy_contract.py`: Restricted policy fails loudly — non-zero exit, no usage output — and the documented Bypass invocation works, per installed PS host; both `.ps1` wrappers now carry in-file Restricted/Bypass/.cmd-fallback guidance, CRLF-pinned) | done + tests (4) |
| W3-9 leftover: Windows lock-owner probe (`windows_lock_open_denied` share-mode probe in `server_editor_host_processes.py`; denied open marks the lock held even without pid attribution, attribution falls back to `list_live_project_editor_pids`, held locks are never deleted — `project_already_open_without_bridge` now reachable on Windows; native share-mode test via ctypes CreateFileW) | done + tests (7) |
| W3-10 leftover: raw-argv echo on argparse failure (`server.py` echoes repr of received argv to stderr on parse error, help exits stay clean — the historical truncation class is now diagnosable at the failure point) | done + tests (3) |
| W3-10 leftover: fail-fast `unity_version_mismatch` (`detect_unity_app_path_for_project` raises with project version, installed versions, and searched roots instead of silently opening the newest install into Unity's upgrade dialog; explicit `--unity-app` still overrides; unknown project version keeps the newest-install fallback) | done + tests (4) |
| W3-13 docs pass (README: native-Windows Python precheck, PowerShell-first quickstart with `.\` + `$env:TEMP` ahead of the cmd.exe variant, `.ps1` Bypass invocation, Windows uninstall variant, bash-only smoke-runner honesty note, Windows-aware Agent Setup Prompt platform rule, stale `v0.3.21` → "latest tagged release"; `Agents.md` public entrypoints now list the `.cmd`/`.ps1` flavors) | done |
| W3-12 live colleague-machine session via `docs/archive/retros/INSTALL_RETRO_PROMPT.md` | **open — external input; the only remaining Wave-3 item.** `STATUS.md` cross-platform row updated to "templates provided; CI-exercised"; the live-host claim stays conservative until a green session |

Wave 3 scope notes: suite now 387/387 green (8 skips: 4 pre-existing native-Windows + 2 `.ps1` policy behavior + 2 native share-mode; all run on the Windows CI leg). `scripts/testing/process_support.run_with_timeout` gained `input_text` (stdin delivery) and explicit UTF-8 decode of child output, per the helper-subprocess discipline. The e2e file needs no CI wiring — `unittest discover` picks it up on all three OS legs.

**First Windows CI e2e run (2026-07-11) immediately caught a live wall — validating the whole Wave-3 premise**: `ensure-ready` failed fast with the correct `unity_app_not_found` payload, but the `.cmd` wrapper reported **exit 0**. Root cause: all three wrappers terminated the run block with a bare `exit /b`; a top-level batch ending that way under `cmd /c` sets the process exit code to 0 regardless of ERRORLEVEL (explicit codes like `exit /b 9009` propagate fine — which is why the Wave-1 broken-PYTHON test stayed green and the gap survived until a test asserted a nonzero *python* exit through the chain — exactly the "exit codes pass vacuously" complicity predicted in §5). Fix: run block moved to the end of each wrapper so the delegated python invocation is the final executed line and its ERRORLEVEL becomes the process exit code; contract test now forbids bare `exit /b` and requires the natural-end shape; a native behavioral test asserts nonzero propagation (`argv as received` visible through the real chain); `skills/cross_platform_shell` §12 corrected — it had recommended the buggy pattern.

## 5f. Runner-squeeze wave (2026-07-11, after the first green Windows e2e)

After the Windows leg went green, the remaining "what else can this runner prove without Unity" gaps were implemented as four more e2e layers. Each targets a layer a real colleague exercises in the first ten minutes that CI had never executed:

| Squeeze | What it proves | Status |
| --- | --- | --- |
| Config-to-connection (`tests/test_installed_delegate_e2e.py`) | CI previously tested only the REPO copy of the launcher; colleagues run the INSTALLED one. Leg 1: the refresh launcher (`run_installed_or_refresh_xuunity_mcp.{cmd,sh}`) performs a real install into a sandboxed neutral dir and serves MCP stdio from the installed delegate in the same process chain. Leg 2: `init_...sh --install-claude-config` writes a sandboxed client config, and the test spawns *exactly the command written into the config* (cmd.exe env-indirected call on Windows, `bash -lc exec` on POSIX) from a neutral cwd and requires `initialize` + a tool call to answer — the historical "registered command cannot start on this host" class (Appendix A #9) now has an executable guard | done + tests (2) |
| Verbatim README PowerShell 5.1 quickstart (`tests/test_readme_quickstart_windows_e2e.py`) | The documented `.cmd`-from-PowerShell sequence, run under real `powershell.exe` with NO `-ExecutionPolicy Bypass` (policy immunity) on a spaces+Cyrillic project: `setup-plan > plan` (asserts the plan file really came out UTF-16LE-BOM — retro class 2 exercised live, not dodged), `setup-apply --plan-file`, `validate-setup`, manifest assertion | done + tests (1, Windows leg) |
| Host↔bridge file-IPC against a live second process (`tests/test_file_ipc_bridge_simulator_e2e.py` + `tests/bridge_ipc_simulator.py`) | A simulator subprocess plays the Unity side (heartbeat state + inbox/outbox responder), and `tools/call unity_status` through the real launcher round-trips the full host transport (state liveness via `editor_pid`, request write, response poll/parse/unlink) on the actual filesystem — the first cross-process exercise of the file-IPC path anywhere. Plus a two-process torn-read stress: 400 rewrites through the production `write_json` while a concurrent reader asserts it never parses a torn payload (W2-7 executed against real NTFS on the Windows leg) | done + tests (2) |
| Hostile console codepages (`tests/test_ru_console_codepage_e2e.py`) | Wall #3 re-created for the whole `cmd.exe → .cmd → python` chain via `PYTHONIOENCODING=<cp>:strict`, which outranks UTF-8 mode for stdio: CLI setup-plan with a Cyrillic path under cp866 (RU OEM) and cp1252 (Western ANSI, where Cyrillic cannot encode at all), an MCP stdio round-trip under cp866 (UTF-8 stdin frames must still decode), and the ensure-ready error path staying clean — a regression of the stdio reconfigure now fails these legs loudly | done + tests (3, Windows leg) |

Runner-squeeze scope notes: suite now 398 green (13 skips on macOS — the 4 new Windows-only legs plus the pre-existing native set; all run on the Windows CI leg). No workflow changes needed — `unittest discover` picks the files up on all three OS legs. What the runner still cannot prove (unchanged): a real Unity boot and first package import, the live C# bridge, and corporate-machine conditions — item 12 (live colleague session) remains the only converter from "CI-exercised" to "supported".

**The first config-to-connection run on the Windows leg immediately caught the second live wall**: the `if defined X (call "%X%\...cmd") else (call "...")` arg that `--install-claude-config`, the Codex block, and all six Windows client templates persisted can never spawn through a standard MCP client. Clients (Node libuv, Python `list2cmdline`) quote argv with the C-runtime rules — embedded quotes become `\"` — and cmd.exe misparses that: the runner reported `'\"C:\...\run_installed_or_refresh_xuunity_mcp.cmd\"' is not recognized`. Every prior "Windows client config" fix (W1-6 incl. the bash→cmd.exe mismatch replacement) validated the JSON shape, never a spawn, so the class survived three waves. Fix: configs now persist the install-time-resolved native launcher path as its own argv entry (`["/d", "/c", "call", "<dir>\run_installed_or_refresh_xuunity_mcp.cmd"]`; `cygpath -w` for MSYS-form dirs per rule 7) across the installer's Claude JSON + Codex TOML writers, all six `templates/clients/*.windows.*`, INSTALL.md, and the six client docs pages; runtime env-var indirection is gone — the installer resolves overrides (`CLAUDE_TOOLS_HOME`, `XUUNITY_LIGHT_UNITY_MCP_NEUTRAL_INSTALL_DIR`, …) at write time instead, because an unquoted `%VAR%` in an arg breaks on expansion when the value contains spaces and a quoted one cannot survive client quoting. Guards: `tests/test_windows_client_config_contract.py` (all templates: quote/paren-free four-arg shape) and the config-to-connection e2e itself; `skills/cross_platform_shell` gained rule 13.

## 6. Recommended fix plan

### Wave 1 — unblock colleagues (each item unit-testable on the GitHub Windows runner, no Unity needed)
1. **`.cmd` correctness**: fix `exit /b %ERRORLEVEL%` (5 sites × 3 files), reject WindowsApps stub interpreters, add the ≥3.10 gate, tolerate quoted `PYTHON`.
2. **UTF-8 everywhere**: stdio `reconfigure` in `server.py`; `PYTHONUTF8=1` in all launchers + client templates; `encoding="utf-8", errors="replace"` on every subprocess and file read/write; `[Console]::OutputEncoding` prefix for PS helpers; keep `ensure_ascii=True` for CLI JSON or reconfigure stdout.
3. **Self-hosting Windows install**: Windows branch for `--install-claude-config` (mirror the Codex one); ship delegate files as CRLF templates written by Python (no heredocs, `subprocess` not `execv`); sync `run.cmd`/`run.ps1` in `server_launcher.py`; refresh falls back to the native `.py` path instead of dying without Git Bash.
4. **Unity discovery**: `*/Editor/Unity.exe` glob, Hub `secondaryInstallPath.json`/`editors-v2.json`, searched-roots in the error.
5. **ensure-ready first-run honesty**: fail fast on `not_declared`; include `not_declared` in the post-timeout diagnosis; detect missing `git.exe` before opening the editor; document/raise the first-open timeout.
6. **Recovery commands**: platform-matched launcher name via `launcher_display_name()`, quoted args or args-array everywhere.

### Wave 2 — reliability
7. Atomic writes both sides (Python `write_json` temp+`os.replace`; C# temp+`File.Replace` for `bridge_state.json`/outbox), retry-until-deadline on response reads, unlink only after successful parse.
8. PID identity re-check (command line targets the project) before any `taskkill /F`; add `/T`.
9. Subprocess `timeout=` + `CREATE_NO_WINDOW` across all helpers; Windows lock-owner probe (editor list + exclusive-open attempt).
10. devmode cross-drive fallback + forward-slash `file:` deps; raw-argv echo on argparse failure; fail-fast `unity_version_mismatch` instead of newest-install fallback.

### Wave 3 — close the loop (process)
11. **[done 2026-07-11, §5e]** **Windows CI e2e smoke without Unity**: spawn the server via `xuunity_light_unity_mcp.cmd` as a real process, drive `initialize`/`tools/list` over stdio (this also gives `serve_stdio` its first test anywhere), assert exit codes; add a Cyrillic+spaces project-path fixture; run one `.ps1` leg under stock Windows PowerShell 5.1 default policy; assert `ensure-ready` fails fast with no Unity installed.
12. **[open — the last Wave-3 item]** **One live validation session on a colleague's real Windows machine** using `docs/archive/retros/INSTALL_RETRO_PROMPT.md` to capture evidence — this is the explicitly deferred item from 2026-06-17 and the only thing that converts "templates provided" into "supported". Repeat after Wave 1 lands; upgrade `STATUS.md:207` to live-host proof only on green.
13. **[done 2026-07-11, §5e]** Docs pass: PowerShell-first Windows quickstart (with `.\` and `$env:TEMP`), native prerequisites check, Windows variants for verify/uninstall/smoke, `.cmd`/`.ps1` added to `Agents.md` "Public shell entrypoints", Windows-aware Agent Setup Prompt.

---

## Appendix A — documented failure history (from retros; all fixed offline-only)

| # | Class | Retro | Fix commit | Real-Windows verified |
| --- | --- | --- | --- | --- |
| 1 | Wrapper delegates to missing `python3` | 2026-06-09 v1 | `c7d096d` | no |
| 2 | Plan-file UTF-16/BOM rejection | 2026-06-09 v1 | `c7d096d` | no |
| 3 | `os.kill(pid,0)` liveness invalid on Windows | 2026-06-09 v1 | `c7d096d`+`3297e85` | no |
| 4 | ctypes x64 truncation → `SystemError` poisoning | 2026-06-10 | `3297e85` | no |
| 5 | Mass process kill under MSYS | 2026-06-10 | `3297e85` | no (`--dry-run` still deferred) |
| 6 | WSL↔Windows editor discovery/attach | 2026-06-09 v2 | `c7d096d`,`0c95d84` | no |
| 7 | Project-root truncation via Git-Bash argv | 2026-06-17 | none (mitigations `b0ea846`) | no — root cause never proven |
| 8 | `.ps1` ExecutionPolicy block | 2026-06-17 | docs only (`b0ea846`) | no |
| 9 | Codex config wrote bash launcher on Windows | 2026-06-17 | `b0ea846` (+`63c3b40`) | no |
| 10 | validate-setup "ready" ≠ resolved; heartbeat dead-wait | 2026-06-17 | partial (`b0ea846`); `not_declared` still unhandled | no |
| 11 | Stale session/bridge state closeout ambiguity | 2026-06-09 v2 / 06-17 | `b0ea846` fast path; force-recovery deferred | no |
| 12 | Recovery-hint path rendering | (follow-on) | `81f4f29` — paths fixed, flavor/quoting not | no |

## Appendix B — review provenance

- Lane 1: retro/fix history cross-referenced with `git log`/`git show` (5 retros, 12 classes, fix-commit mapping).
- Lane 2: install surface — all root wrappers, installer, refresh trio, `templates/run.*`, `.gitattributes`, `mcp-server.json`, README/INSTALL/4 client docs, line-by-line as a fresh Windows user.
- Lane 3: server templates — 20+ `server_*.py` files traced end-to-end for the seven Windows hazard categories (discovery, subprocess, paths, IPC, encoding, timeouts, platform branches).
- Lane 4: CI/tests — workflow steps/shells, per-scenario coverage matrix, source-vs-copy and native-execution verification.
- Manual: Unity C# bridge (`FileIpcPaths`, `ResponseWriter`, `BridgeStateWriter`, `BridgeTransportRuntime` incl. `SO_REUSEADDR`/port-0 analysis), `Agents.md` router, `skills/cross_platform_shell` + `safe_process_management` conventions, `STATUS.md`/`ROADMAP.md` claims.
