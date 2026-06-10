# XUUnity Light Unity MCP Install Retro Artifact

Source prompt: https://github.com/FoxsterDev/xuunity-mcp/blob/master/docs/archive/retros/INSTALL_RETRO_PROMPT.md

Date: 2026-06-09

## Analysis Summary

The install flow reached a valid Unity package and bridge configuration state, but it exposed Windows host-helper failures before the bridge could be proven healthy.

Primary first failing step:

- `setup-plan` through `xuunity_light_unity_mcp.sh` failed on Windows Git Bash with `exec: python3: not found`.
- The script had already resolved Python fallback logic, but the non-compact server delegation path still used `exec python3 ...`.
- Passing `--compact-summary` before the command allowed the wrapper to use the resolved Python function and produce a valid setup plan.

Secondary setup friction:

- `setup-apply --plan-file ...` failed when the plan file was captured by PowerShell `Tee-Object`.
- First failure was UTF-16 output: `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff`.
- Second failure was UTF-8 with BOM: `JSONDecodeError: Unexpected UTF-8 BOM`.
- Rewriting the plan as UTF-8 without BOM allowed `setup-apply` to complete.

Runtime readiness failure:

- `ensure-ready --open-editor` failed during running Unity editor discovery.
- On this Windows host, Python `os.kill(pid, 0)` returned `OSError(22, WinError 87)` for valid Unity PIDs and once surfaced as `SystemError`.
- This blocks same-project Unity process detection and should be classified separately from package resolution or bridge enablement.

The package dependency, lockfile entry, bridge config, and Test Framework capability were not the failure source.

## Public GitHub Issue Package

### 1. Issue Title

Windows Git Bash setup and readiness fail when helper delegates to `python3` directly and uses `os.kill(pid, 0)` for Unity PID liveness

### 2. Executive Summary

Installing XUUnity Light Unity MCP on Windows through the README flow mostly succeeded, but several host-helper issues blocked a clean first setup:

1. `setup-plan` failed from Git Bash because the wrapper delegated with `exec python3` even though only `python` was available on PATH.
2. `setup-apply --plan-file` could not read JSON plan files produced by common PowerShell capture paths when they were UTF-16 or UTF-8 with BOM.
3. `ensure-ready --open-editor` failed while detecting existing Unity editor processes because Python `os.kill(pid, 0)` is not reliable as a Windows liveness probe in this environment.

The Unity package itself was declared and resolved, and `validate-setup --include-tests` reported `validation_status: ready`.

### 3. Environment Table

| Item | Value |
| --- | --- |
| OS | Windows |
| Shells used | PowerShell, Git Bash |
| MCP client | Codex |
| Unity version | `6000.3.10f1` |
| Python versions present | `3.12`, `3.11`, `3.10` |
| XUUnity package source | `https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.23` |
| `com.unity.test-framework` | `1.6.0` |
| Project path | `<PROJECT_ROOT>` |
| User home | `<USER_HOME>` |

### 4. Project Topology

Single Unity project:

```text
<PROJECT_ROOT>
  Assets/
  Packages/
  ProjectSettings/
```

The setup plan detected:

```text
workspace_kind: single_project
discovered_project_count: 1
requires_explicit_project_selection_for_apply: false
detected_client: codex
client_context_confidence: high
```

### 5. Installation Route Attempted

The attempted route was README Git UPM setup plus the helper/setup wizard:

```bash
git clone https://github.com/FoxsterDev/xuunity-mcp.git <TEMP_SOURCE>
cd <TEMP_SOURCE>
./xuunity_light_unity_mcp.sh setup-plan --project-root <PROJECT_ROOT>
./xuunity_light_unity_mcp.sh --compact-summary setup-plan --project-root <PROJECT_ROOT>
./xuunity_light_unity_mcp.sh --compact-summary setup-apply --plan-file <PLAN_FILE> --project-root <PROJECT_ROOT> --yes
./init_xuunity_light_unity_mcp.sh --target codex --install-codex-config
./xuunity_light_unity_mcp.sh --compact-summary validate-setup --project-root <PROJECT_ROOT> --include-tests
./xuunity_light_unity_mcp.sh --compact-summary ensure-ready --project-root <PROJECT_ROOT> --open-editor
```

### 6. Expected Behavior

- `setup-plan` should run using the resolved Python interpreter, including `python` or `py -3` fallbacks on Windows.
- `setup-apply` should consume a setup plan produced or captured during normal CLI usage, or clearly reject invalid encodings with a specific recovery message.
- `ensure-ready` should detect an already-open Unity editor for the target project without crashing during PID liveness checks.

### 7. Actual Behavior

#### `setup-plan` direct wrapper failure

```text
./xuunity_light_unity_mcp.sh: line 432: exec: python3: not found
```

This happened even though Windows Python was available as `python`.

#### `setup-plan` with `--compact-summary`

Running with `--compact-summary` before the command worked:

```bash
PYTHON=python ./xuunity_light_unity_mcp.sh --compact-summary setup-plan --project-root <PROJECT_ROOT>
```

The plan reported:

```text
validation_status: ready_to_apply
planned_project_file_changes:
  <PROJECT_ROOT>/Library/XUUnityLightMcp/config/bridge_config.json
planned_user_level_config_changes:
  <USER_HOME>/.codex/config.toml
```

#### Plan file encoding failures

When the JSON plan was captured with PowerShell `Tee-Object`, `setup-apply` failed:

```text
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte
```

After writing as PowerShell `-Encoding utf8`, it failed again because the file had a BOM:

```text
json.decoder.JSONDecodeError: Unexpected UTF-8 BOM (decode using utf-8-sig): line 1 column 1 (char 0)
```

After writing the plan as UTF-8 without BOM, `setup-apply` succeeded.

#### `ensure-ready` PID liveness failure

Existing Unity editor processes were present for the project, but readiness failed while discovering them:

```text
OSError: [WinError 87] The parameter is incorrect

SystemError: <built-in function kill> returned a result with an exception set
```

Stack location:

```text
server_host_platform.py:20, in pid_is_alive
    os.kill(pid, 0)

server_editor_host.py:393, in find_running_unity_editors_for_project
    if pid <= 0 or pid in seen_pids or not pid_is_alive(pid):
```

Direct reproduction outside the helper also showed the same Windows liveness problem:

```text
os.kill(<valid Unity PID>, 0) -> OSError(22, WinError 87)
```

### 8. First Failing Step

First visible failure:

```text
setup-plan direct wrapper delegation
```

Classification:

```text
server_boot_failed
```

Secondary classifications:

```text
unknown_install_failure
process_visibility_restricted
```

`process_visibility_restricted` applies to the later `ensure-ready` failure because the helper could list Unity processes but could not safely confirm PID liveness on Windows through `os.kill(pid, 0)`.

### 9. Timeline Of Attempted Actions

1. Confirmed the Unity project already had `com.xuunity.light-mcp` and `com.unity.test-framework` in `Packages/manifest.json`.
2. Cloned `https://github.com/FoxsterDev/xuunity-mcp.git` into `<TEMP_SOURCE>`.
3. Ran `setup-plan --project-root <PROJECT_ROOT>` from Git Bash.
4. Hit `exec: python3: not found`.
5. Retried with `PYTHON=python`; the same non-compact path still hit `exec python3`.
6. Retried with `--compact-summary` before `setup-plan`; setup plan succeeded.
7. Applied the plan, initially failing due plan file encoding.
8. Rewrote the plan as UTF-8 without BOM; `setup-apply` succeeded and wrote bridge config.
9. Ran Codex config installer; Codex MCP block was added.
10. Ran `validate-setup --include-tests`; it reported ready.
11. Ran `ensure-ready --open-editor`; it failed during Windows PID liveness detection.

### 10. Sanitized Package State

`Packages/manifest.json`:

```json
{
  "com.unity.test-framework": "1.6.0",
  "com.xuunity.light-mcp": "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.23"
}
```

`Packages/packages-lock.json`:

```json
{
  "com.unity.test-framework": {
    "version": "1.6.0",
    "depth": 0,
    "source": "builtin"
  },
  "com.xuunity.light-mcp": {
    "version": "https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.23",
    "depth": 0,
    "source": "git",
    "dependencies": {},
    "hash": "affbd0e4f32acc90cea9cb10a264ec172b97634c"
  }
}
```

### 11. Sanitized MCP Client Config

Codex config after installer:

```toml
[mcp_servers.xuunity_light_unity]
command = "bash"
args = ["-lc", "exec \"<USER_HOME>/.codex-tools/xuunity-mcp/run.sh\""]
required = false
```

### 12. Setup Helper Output Summary

`setup-plan` after workaround:

```text
package_dependency_state: declared
bridge_config_state: missing
test_framework_state.status: supported
test_capabilities_state: supported
validation_status: ready_to_apply
planned_actions:
  write_bridge_config
```

`setup-apply` after no-BOM UTF-8 plan:

```text
action: setup_apply
approved: true
applied_actions:
  write_bridge_config
```

`validate-setup --include-tests`:

```text
package_dependency_state: declared
bridge_config_state.state: enabled
bridge_config_state.enabled: true
test_framework_state.status: supported
test_capabilities_state: supported
validation_status: ready
blockers: []
```

`ensure-ready --open-editor`:

```text
failed during find_running_unity_editors_for_project
root cause observed: Windows os.kill(pid, 0) failed for valid Unity PIDs
```

### 13. Failure Classification

Primary:

```text
server_boot_failed
```

Secondary:

```text
process_visibility_restricted
unknown_install_failure
```

Not indicated by current evidence:

```text
package_source_unreachable
package_manifest_mutation_failed
unity_package_resolve_failed
project_discovery_ambiguous
client_mcp_config_invalid
bridge_not_enabled
optional_dependency_missing
optional_dependency_too_old
unity_compile_error_after_install
```

### 14. Most Likely Causes

1. The wrapper has Python fallback resolution, but the non-compact delegation path bypasses it with `exec python3`.
2. `setup-apply` reads JSON with strict UTF-8 and does not tolerate UTF-8 BOM, while PowerShell capture patterns can create UTF-16 or BOM-bearing UTF-8 files.
3. Windows PID liveness uses POSIX-style `os.kill(pid, 0)`, which is unreliable on this host and Python combination. A Windows-specific API such as `OpenProcess` plus `WaitForSingleObject` would avoid the crash and false negatives.

### 15. Smallest Reproduction Steps

#### Repro 1: wrapper Python delegation

On Windows Git Bash where `python` exists but `python3` does not:

```bash
git clone https://github.com/FoxsterDev/xuunity-mcp.git <TEMP_SOURCE>
cd <TEMP_SOURCE>
./xuunity_light_unity_mcp.sh setup-plan --project-root <PROJECT_ROOT>
```

Expected: setup plan JSON.

Actual:

```text
exec: python3: not found
```

#### Repro 2: Windows PID liveness

With a Unity editor already open for `<PROJECT_ROOT>`:

```bash
./xuunity_light_unity_mcp.sh --compact-summary ensure-ready --project-root <PROJECT_ROOT> --open-editor
```

Expected: existing editor is detected or bridge readiness status is reported.

Actual: helper crashes during process liveness check with `WinError 87` or `SystemError`.

### 16. Attachments Or Logs To Include

Include these sanitized artifacts:

- `setup-plan` JSON after `--compact-summary`.
- `validate-setup --include-tests` JSON.
- `ensure-ready --open-editor` traceback.
- Relevant lines from `Packages/manifest.json`.
- Relevant lines from `Packages/packages-lock.json`.
- Sanitized Codex MCP config block.
- Python direct `os.kill(pid, 0)` reproduction output for valid Unity PIDs.

### 17. Redaction Notes

Redacted:

- User home path as `<USER_HOME>`.
- Unity project root as `<PROJECT_ROOT>`.
- Temporary source checkout as `<TEMP_SOURCE>`.
- Private project name and local machine details.

Kept:

- Unity version.
- Public GitHub package URL and tag.
- Package names.
- Error codes and small traceback excerpts.
- MCP client type.

### 18. Maintainer Questions That Remain

1. Should `run_server_with_optional_compact_summary` use the resolved `PYTHON_BIN` or `python3` shell function in all paths, including non-compact `exec`?
2. Should `setup-apply --plan-file` accept UTF-8 with BOM, or should `setup-plan` provide a dedicated `--output` flag to avoid shell encoding pitfalls?
3. Should Windows process liveness avoid `os.kill(pid, 0)` and use a platform-specific implementation?
4. Should `ensure-ready` degrade gracefully to process-listing evidence when PID liveness checks fail instead of crashing?
5. Should the README Windows section mention putting `--compact-summary` before the command name only if this remains a supported workaround?

### Issue-Ready Summary

On Windows, XUUnity MCP setup can fail before bridge validation even when the Unity package is already declared and resolved. The first failure is `xuunity_light_unity_mcp.sh setup-plan` delegating with `exec python3` instead of the resolved Python fallback. After working around that with `--compact-summary`, setup and validation succeeded, but `ensure-ready` crashed during Unity editor process discovery because Windows `os.kill(pid, 0)` failed for valid Unity PIDs with `WinError 87` or `SystemError`.

Smallest next maintainer action: fix the helper's Python delegation path first, then replace Windows PID liveness checks with a Windows-specific API and add a regression test for Windows hosts where `python` is present but `python3` is not.
