---
name: safe-process-management
description: Rules and guidelines for safe process matching, liveness checking, and process termination on Windows, WSL, MSYS/Cygwin, macOS, and Linux.
---

# Safe Process Management Guidelines

This skill defines the rules and best practices for process querying, validation, and termination. These rules MUST be followed to prevent catastrophic failures, such as system-wide application shutdowns or OS instability, when working with platform adapters and process command line heuristics.

---

## 1. Fail-Safe Defaults on Exception Handling

When implementing try-except blocks for process filtering, command-matching, or liveness checks, the fallback logic **MUST ALWAYS** default to the safest possible state.

- **Process Matching / Heuristics:** If a string match, command line parse, or regex operation throws an exception (such as `SystemError` or `ValueError`), the handler **MUST** assume the process does **NOT** match the target. Default to `False`.
  ```python
  # INCORRECT (Catastrophic fallback - matches everything on string crash)
  try:
      is_unity = command.endswith("/Unity")
  except Exception:
      is_unity = True  # NEVER DO THIS

  # CORRECT (Safe fallback - ignores on string crash)
  try:
      is_unity = command.endswith("/Unity")
  except Exception:
      is_unity = False
  ```
- **Liveness Checking:** If a process visibility check throws an exception, assume the process is **dead** or unreachable. Default to `False`.
- **Process Terminations:** Never trigger bulk terminations on processes that did not explicitly pass a strict, positive validation whitelist.

---

## 2. Process Liveness Check Rules (`pid_is_alive`)

### Avoid `os.kill(pid, 0)` on Windows-like Systems
- `os.kill(pid, 0)` is not natively supported on Windows.
- On hybrid POSIX environments running on Windows (e.g. MSYS, Cygwin, Git Bash), calling `os.kill(pid, 0)` on a native Windows process is unreliable and can raise `SystemError` or return incorrect results.
- **Rule:** If `os.name == "nt"` or `sys.platform in ("win32", "cygwin", "msys")`, use Win32 API calls (`OpenProcess`) or native tools (`tasklist`) instead of `os.kill`.

### Declare Explicit ctypes Signatures
- When calling Windows Kernel32 APIs via `ctypes`, always declare argument types (`argtypes`) and return types (`restype`).
- Without this, `ctypes` defaults to 32-bit `int` types, which truncates 64-bit handles on Windows x64, corrupts the stack, and leaves latent exception flags on the Python thread.
  ```python
  import ctypes
  from ctypes import wintypes

  kernel32 = ctypes.windll.kernel32
  kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
  kernel32.OpenProcess.restype = wintypes.HANDLE
  ```

### Clear Thread Exception States
- In `except` blocks dealing with `ctypes` or low-level OS calls, always clear the thread's exception state to prevent subsequent string operations (like `str.endswith` or `str.replace`) from failing with `SystemError`.
  ```python
  try:
      import ctypes
      if hasattr(ctypes, "pythonapi") and hasattr(ctypes.pythonapi, "PyErr_Clear"):
          ctypes.pythonapi.PyErr_Clear()
  except Exception:
      pass
  ```

---

## 3. Process Termination Rules (`terminate_editor_pid`)

- **Route Windows-like PIDs through `taskkill`:** For native Windows, Cygwin, and MSYS environments, process termination must be routed through `taskkill` / `taskkill.exe`.
- **Never call POSIX `os.kill(pid, signal.SIGTERM)` on Windows PIDs under MSYS/Cygwin:** This can terminate random processes or kill the entire process group, shutting down all user applications.
- **Double-Validate PID:** Ensure the PID is strictly greater than `0` and explicitly matches the application to be terminated before calling any kill command.
