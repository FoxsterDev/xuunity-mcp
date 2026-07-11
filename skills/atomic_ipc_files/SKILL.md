---
name: atomic-ipc-files
description: Writer+reader co-design rules for every file another process polls (bridge_state.json, inbox/outbox, journal, batch and scenario results) across the Python host and the C# editor package, including Windows sharing-violation behavior and version-skew tolerance.
---

# Atomic IPC File Guidelines

The host and the editor exchange state through polled files. A plain write lets the poller observe a half-written file (truncated JSON) or hit a Windows sharing violation mid-write; a naive reader can then *consume* the torn file and lose the response forever. Atomicity here is a **writer+reader co-design** — fixing only one side still loses data under version skew, because old writers and new readers (and vice versa) coexist across package releases.

---

## 1. Writers Publish Atomically

- Write to a temp file **in the same directory**, then rename over the destination: Python `server_core.write_json` (temp + `os.replace`), C# `XUUnityLightMcpAtomicFileWriter` (temp + `File.Replace`/`File.Move`).
- The temp name must not match any reader's scan glob: `<name>.<uuid>.tmp` never matches `*.json`, so the editor request pump and result scanners cannot pick up a partial file.
- C# side: `File.WriteAllText` is allowed **only inside** `XUUnityLightMcpAtomicFileWriter` — `tests/test_atomic_ipc_contract.py` enforces the single-call-site invariant over the whole `Editor/` tree. Route new polled-file writers through it; do not add direct writes.

## 2. Contention Handling Depends on the Writer's Thread

- On Windows, `os.replace`/`File.Replace` can fail transiently while a poller briefly holds the destination open (readers poll `bridge_state.json` at up to 5 Hz during active operations).
- **Host process (Python):** bounded sleep-retry is fine (`write_json`: 5 × 50 ms on `PermissionError`), then fall back to a direct write.
- **Editor main thread (C#):** never sleep — immediate retries only, then fall back to the legacy in-place write. The torn read that fallback can produce is exactly what rule 3 makes survivable. (See editor-main-thread skill.)

## 3. Readers Retry Until Deadline, Delete Only After Parse

- A polled response that fails to parse or open (`OSError`, `ValueError` — covers `JSONDecodeError`, `UnicodeDecodeError`, `PermissionError`) is **mid-write, not garbage**: leave it on disk and keep polling until the operation deadline.
- Unlink only after a successful parse. A `finally: unlink()` around the read converts one torn read into a permanently lost response and a full operation timeout (this exact bug shipped; fixed in `FileIpcBridgeTransport.invoke` and `try_take_recovered_response`).
- Reader tolerance is also the **version-skew compatibility layer**: editors running an older package still write non-atomically, and the atomic writer's editor-side fallback is non-atomic by design.

## 4. Regression Guards

`tests/test_atomic_ipc_contract.py` holds the contract: `write_json` atomicity/retry/fallback and temp-name glob safety, transport retention of partial responses plus mid-flight completion pickup, the C# single-writer sweep, and `.meta` GUID uniqueness for new package files. Extend it when adding a new polled file or a new writer.
