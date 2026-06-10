# Retro: Windows Process Discovery and Termination Catastrophe (2026-06-10)

## 1. Executive Summary
During a project readiness check (`ensure-ready --open-editor`) on a Windows machine running Git Bash (MSYS), a low-level `SystemError` crashed the process-matching string engine, causing the AI agent to apply a flawed fallback heuristic. This fallback marked all running user processes as "Unity editors." During cleanup, the server attempted to terminate these processes. Because MSYS evaluates `os.name` as `"posix"`, the server used POSIX `os.kill(pid, signal.SIGTERM)` on native Windows process IDs, causing a system-wide termination of all user-owned applications (including tray icons, terminals, and editors).

This retro documents the root causes, the applied fixes, and proposes a new safety feature: `--dry-run` mode for process termination in MCP clients.

---

## 2. Root Cause Analysis

### A. ctypes Signature Truncation on x64
The original implementation did not define `argtypes` and `restype` for Win32 API functions loaded from `kernel32.dll`. Under 64-bit Python, `ctypes` assumed 32-bit return values, truncating 64-bit process handles. This caused subsequent Win32 calls (like `GetExitCodeProcess`) to fail and leave the Python C-level thread exception state corrupted.

### B. Latent Thread Exception Poisoning (`str.endswith` Crash)
Because the `ctypes` call failed and did not cleanly reset CPython's internal thread error indicator, the next C-implemented function called in Python (in this case, `command_for_match.endswith("/Unity")`) raised a `SystemError: <method 'endswith' of 'str' objects> returned a result with an exception set` despite the string method arguments being completely valid.

### C. Overly Permissive Heuristic Fallbacks
Encountering the `endswith` crash inside the editor-matching loop, the executing AI agent attempted to hotfix the helper code by adding a `try-except` guard. However, this guard defaulted to `True` on exceptions (e.g. `except Exception: is_unity = True`), which incorrectly classified every running system process as a Unity editor.

### D. MSYS/Cygwin POSIX Signal Execution on Windows PIDs
When the server called `terminate_editor_pid()`, it checked `os.name == "nt"` to determine whether to use `taskkill` or `os.kill`. In MSYS/Cygwin Python, `os.name` is `"posix"`. The code fell into the `else` block and ran POSIX `os.kill(pid, signal.SIGTERM)` on all PIDs in the matched list. In MSYS, this successfully routed the terminate signals to all Windows applications owned by the user, causing a total session crash.

---

## 3. Recommended Feature: `--dry-run` Mode for MCP Process Actions

To prevent agents from making destructive process-control decisions on native hosts, MCP clients and server helper tools should support a safe `--dry-run` mode.

### What is `--dry-run` Mode?
`--dry-run` is a command line flag (or JSON argument payload) passed to lifecycle-altering commands (like `ensure-ready`, `recover-editor-session`, and process termination helpers).
When active, the tool performs all process scanning, heuristic matching, and liveness discovery, but **skips the actual execution of termination commands** (`taskkill`, `kill`, etc.).

### How It Helps the AI Agent
1. **Validation of Targets:** The agent can run `ensure-ready --dry-run` first, inspect the JSON output, and verify that the target PIDs/commands represent *only* the intended Unity editor process.
2. **Safety Gates:** If the agent sees system PIDs (like Explorer or browser processes) in the target list, it can abort the operation immediately before any damage is done.

### Implementation Blueprint

#### A. Command Line Interface (CLI)
Add a `--dry-run` flag to the server/helper args:
```bash
# Preview what editors would be killed during session recovery
xuunity-mcp recover-editor-session --dry-run
```

#### B. JSON Response Structure
When `--dry-run` is set, the command should return a structured report instead of executing the kill:
```json
{
  "dry_run": true,
  "action": "terminate_stale_editors",
  "targets_detected": 1,
  "targets": [
    {
      "pid": 12345,
      "command": "D:\\ProgramFiles\\Unity\\Editor\\Unity.exe -projectPath D:\\Project",
      "status": "would_terminate",
      "is_valid_editor": true
    }
  ],
  "execution_prevented": true
}
```

#### C. Code Integration
Pass a `dry_run: bool` parameter down to process termination functions:
```python
def terminate_editor_pid(pid: int, timeout_ms: int, dry_run: bool = False) -> bool:
    if pid <= 0 or not pid_is_alive(pid):
        return True

    if dry_run:
        print(f"[DRY-RUN] Would terminate process {pid}")
        return True  # Simulate success without killing

    # ... actual termination logic ...
```
All recovery, setup, and test runner setup flows should check if `--dry-run` is active and log intended modifications without mutating host process states.
