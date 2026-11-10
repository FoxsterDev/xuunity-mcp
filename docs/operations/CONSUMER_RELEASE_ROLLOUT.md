# Consumer Release Rollout

Use `scripts/testing/run_consumer_rollout.py` when one published Git package
release used by Unity Package Manager (UPM) must be adopted by several Unity
projects without turning an unvalidated canary into portfolio-wide edits.

The helper is deliberately separate from release publication. It never
commits, pushes, tags, publishes, or repairs an unexpected result. Consumer
manifest and lock changes remain local for their owners to review.

## Safety Model

The workflow is ordered and fail-closed:

1. Reconcile explicit project roots with an ignore-independent manifest scan.
2. Freeze the denominator, package pins, Git state, and workspace dirty paths.
3. Prove the selected Unity version, batch license, write access, global
   process visibility, unique artifact directory, and cleanup owner.
4. Update and compile only the canary project.
5. Fan out the exact published tag and commit hash only after the canary passes.
6. Validate the remaining clean projects serially while flushing an atomic
   ledger after every state transition.
7. Stop on the first unexpected result and return evidence for root review.

The helper refuses a dirty canary. Other projects whose manifest or lock was
already dirty are recorded as `skipped_dirty` and never modified. Newly
discovered projects require explicit root review through `--accept-discovered`;
they are not silently omitted or silently adopted. Use repeatable
`--exclude-root` only for a reviewed clone, experiment, archive, or other tree
that is known not to be an adoption target. Tool-owned `.claude`, `.codex`, and
`.agents` trees are pruned automatically so worktree copies do not inflate the
consumer denominator.

## Plan

Planning performs the Unity license probe after the inventory, write, version,
and global-process checks are clear; it does not change package files. Pass
every expected project explicitly and also provide the common search root:

```bash
python3 scripts/testing/run_consumer_rollout.py plan \
  --search-root /path/to/unity-workspace \
  --expected-project-root /path/to/unity-workspace/MainProject \
  --expected-project-root /path/to/unity-workspace/SecondProject \
  --exclude-root /path/to/unity-workspace/ReviewedNonConsumerTree \
  --canary-project-root /path/to/unity-workspace/MainProject \
  --release-tag v0.4.0 \
  --release-commit 0123456789abcdef0123456789abcdef01234567 \
  --unity-app /path/to/Unity \
  --run-dir /path/to/private-rollout-evidence
```

Some projects rewrite a file on every batch import, for example a generated
settings asset or a scripting-define list. Declare each such file with a
repeatable `--expected-churn <glob>`, relative to the git root or to a project
root. A matching new dirty path is reported under `expected_churn_paths` and
does not stop the run; any other new path still does. Keep the globs to single
files. `resume-project` accepts the same option for churn found mid-run, so the
ledger never needs a manual edit.

`--unity-app` accepts the Unity application/install path understood by the
normal XUUnity host discovery. Every included project must declare the same
exact Unity editor version in `ProjectSettings/ProjectVersion.txt`.

The compact JSON result is the default decision surface. `--output full`
includes the complete frozen inventory and preflight evidence. The run
directory contains:

- `consumer_rollout_ledger.json` — atomic resumable state
- `worker_task_packet.json` — exact bounded-worker contract
- one Unity log and one process log per attempted project

Credential-shaped process arguments such as access tokens, API keys, and
passwords are replaced with `[REDACTED]` before process evidence is persisted.

The task packet is provider-neutral. Host automation may bind it to a suitable
bounded executor, but model names, private project lists, and host-specific
operating preferences do not belong in this public repository.

## Execute

Execution requires a second exact tag confirmation:

```bash
python3 scripts/testing/run_consumer_rollout.py execute \
  --ledger /path/to/private-rollout-evidence/consumer_rollout_ledger.json \
  --confirm-release-tag v0.4.0
```

The helper writes the canary manifest and lock, verifies that both use the
published tag and full release commit, proves the previous tag/hash are gone,
then launches direct Unity batchmode resolve/compile/quit. Only a zero exit,
no known compiler-failure marker, unchanged package files, unchanged tag/hash,
and no new unowned workspace side effect can pass.

After the canary passes, the same exact pin is written to every remaining
clean project. Validation stays serial. A later failure leaves already passed
rows intact and pending rows in the ledger.

The per-project timeout is clamped to the remaining overall deadline. If the
deadline expires after the canary, the helper stops before portfolio fan-out.

Batch compiles leave detached `VBCSCompiler` servers behind. After each
project the helper records every compiler server that was not running at
planning time in the ledger's `compiler_servers`. When the run completes, it
closes the ones whose command still matches the recorded one and lives under
the selected Unity install; a server from another install, a changed command,
or any live Unity editor (which may share the server) leaves them open. The
compact summary reports `compiler_servers_open`. After a stopped run, close them
with:

```bash
python3 scripts/testing/run_consumer_rollout.py close-compiler-servers \
  --ledger /path/to/private-rollout-evidence/consumer_rollout_ledger.json
```

## Resume After Root Review

An unexpected result is terminal for the bounded worker. The root operator
must diagnose it. If a timed-out Unity process remains, use the separate
cleanup command first:

```bash
python3 scripts/testing/run_consumer_rollout.py cleanup-owned \
  --ledger /path/to/private-rollout-evidence/consumer_rollout_ledger.json \
  --project-id ProjectName-stableid
```

Cleanup is not a broad Unity kill. It re-lists processes and requires the
recorded PID to still be a Unity main process with the exact project root and
unique log path. A foreign, reused, invisible, worker, or otherwise ambiguous
PID is refused without termination.

After root diagnosis and any verified cleanup, explicitly re-arm only the
failed row:

```bash
python3 scripts/testing/run_consumer_rollout.py resume-project \
  --ledger /path/to/private-rollout-evidence/consumer_rollout_ledger.json \
  --project-id ProjectName-stableid \
  --confirm-release-tag v0.4.0
```

The previous attempt remains in `attempts`. A resumed `execute` skips a prior
pass only when its tag/hash, package-file fingerprints, and Unity log artifact
still match the ledger.

## Compact Summary

```bash
python3 scripts/testing/run_consumer_rollout.py summary \
  --ledger /path/to/private-rollout-evidence/consumer_rollout_ledger.json
```

The compact result includes the release, frozen denominator, preflight blocker
codes, canary state, per-state totals, first unproven project, artifact paths,
and next action. Use `--output full` only when diagnosing from the detailed
inventory, command, process, or workspace evidence.

## Known Limits

- The batch compile proves Git UPM resolution and script compilation. It does
  not replace project-specific EditMode, PlayMode, UI, or product validation.
- Pre-existing dirty files are preserved in the frozen workspace baseline.
  The helper detects new dirty paths, but it cannot attribute concurrent edits
  made later to a file that was already dirty before planning.
- Every project in one ledger must use the selected Unity version. Split mixed
  Unity versions into separate ledgers.
- A batch-license or global-Unity-process blocker stops before package
  mutation. Do not weaken the preflight to force a rollout through shared
  licensing state.
