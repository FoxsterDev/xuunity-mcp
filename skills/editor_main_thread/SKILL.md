---
name: editor-main-thread
description: Rules for C# bridge code that runs on the Unity editor main thread (heartbeat, request pump, transport, scenario ticks) — the bridge must be invisible in the editor, so no sleeping, no unbounded blocking I/O, and fallback-over-wait on contention.
---

# Editor Main-Thread Guidelines

Everything the bridge does per tick runs on the editor main thread: `XUUnityLightMcpBridgeBootstrap` subscribes to `EditorApplication.update` and drives the heartbeat (2 s), the request pump (0.5 s), lifecycle and scenario ticks. Any blocking call there is a frame stall the user feels as editor lag. The bridge being invisible in the editor is a product requirement, not an optimization.

---

## 1. Never Sleep on the Main Thread

`Thread.Sleep` in tick-reachable code is forbidden. A sleep-based retry converts rare contention into periodic frame stalls (a 5×20 ms retry loop in the atomic writer stalled heartbeats whenever the host poller held `bridge_state.json` — caught in user review, 2026-07-11). On contention, **fall back instead of waiting**: immediate retries, then degrade to the legacy behavior the host side already tolerates (see atomic-ipc-files skill rule 3).

`tests/test_atomic_ipc_contract.py::test_no_main_thread_sleeps_in_editor_package` sweeps the whole package; `XUUnityLightMcpGameViewUtility` (on-demand screenshot settling) is the single allowlisted pre-existing exception — do not widen the allowlist without the same on-demand-only justification, and prefer converting it to a frame-deferred capture.

## 2. Blocking I/O Needs a Bound

- Synchronous socket sends from the main thread must set a send timeout first: `TcpClient.SendTimeout` before writing a response (`TryWriteResponse` uses 5000 ms) — a dead peer with a full send buffer otherwise freezes the editor until the OS-level TCP timeout.
- Blocking accepts/reads belong on a dedicated background thread (`AcceptLoop` pattern), never in a tick.
- File I/O in ticks is bounded by design: one small-file write per heartbeat, one directory scan of a normally-empty inbox per pump.

## 3. Ticks Are Throttled and Early-Out

- All periodic work goes through the interval gates in `XUUnityLightMcpBridgeBootstrap.OnUpdate` (heartbeat/pump intervals from bridge config) — never do per-frame work directly on `EditorApplication.update`.
- Tick bodies must early-out cheaply when idle (`LifecycleMonitor.Tick`, scenario scheduler). New tick work needs the same shape: field checks first, I/O only when something is actually pending.

## 4. Keep the Hot Path Allocation-Light

Per-tick allocations add up at editor frame rates. Resolve once and cache what cannot change within a domain (`WriteHeartbeat` caches the editor pid instead of allocating `Process.GetCurrentProcess()` every heartbeat); expensive probes are memory-cached and refreshed on invalidation, not per tick (`XUUnityLightMcpHealthProbe.EnsureCurrentReport`).
