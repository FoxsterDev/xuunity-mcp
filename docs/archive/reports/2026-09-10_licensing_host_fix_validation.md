# Host licensing fix validation — 2026-09-10

Scope: host templates, host tests, operator diagnostics, and a read-only launch
smoke checker. The consumer Unity package and installed helper were not edited.

## Implemented behavior

- Normalize discovered and explicit OS pipe names to editor channel names while
  preserving redacted discovery and forwarding fingerprints.
- Serialize probes with a per-user OS lock and recheck the shared executable /
  version cache after acquisition. Reuse verified live-editor entitlement
  evidence without claiming batch entitlement. Refuse competing GUI launches
  promptly with `licensing_busy`.
- Expose licensing state in status, readiness, and launch results. Block readiness
  on package refusal or unrecovered licensing failure. Detect the live-observed
  licensing-client connection-loss message and identify external launch failures.
- Use one accepted setup-plan / setup-apply bridge recovery recipe.
- Split recovered licensing startup errors from build errors while retaining
  Unity's original total_errors field.

## Verification

| Check | Result |
| --- | --- |
| Full host test runner | 1,073 tests run; 14 skipped; zero failures/errors |
| Focused licensing regressions | 43 tests passed |
| Exact-channel canary after all editors were closed | Passed: wrapper ownership, forwarded channel connection, and licensed entitlement |
| Live status summary | Licensed and healthy; no blocking reasons; no active probe |
| 12-project sweep with licensed editors already live | 12 licensed_editor_live skips; zero attempted Unity probe launches |
| Real 12-project probe sweep with all editors closed | One Unity probe launch; 11 cache hits |
| Competing GUI launch during the real probe | Refused with licensing_busy in 0.0019 seconds |
| GUI recovery after the sweep | Both original working editors restored, licensed, and connected to their exact forwarded channel |
| Missing forwarded-channel log line | Absent in all successful GUI mechanism checks |

The single real batch probe timed out (exit 124) and was classified as
licensing_client_ipc_failure. This is evidence that serialization and GUI
isolation worked, not proof of successful batch licensing. The available Hub
session supports the GUI fallback; batch entitlement remains unproven on this
host. No repeated probe storm was launched.

A separate task-owned worktree editor was found blocked during licensing
initialization and showing a connection-loss dialog. It was closed under
explicit user authorization. The connection-loss message now has a dedicated
startup classification and overrides an earlier licensed state until fresh
entitlement evidence confirms recovery.

The fixed source runtime was used for live validation. Existing installed or
worktree copies do not gain these changes until their normal synchronization or
release flow applies them; consumers requiring the fix immediately should use
the updated source runtime.
