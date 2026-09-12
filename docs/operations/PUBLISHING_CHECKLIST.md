# Publishing Checklist

Date: `2026-07-01`
Status: `manual follow-up after repo commit`

These items are part of the search/discovery plan but cannot be completed only
through repository file edits.

## Hard Release Rule

Every MCP release must update the public site before the release tag is pushed.
Treat the GitHub Pages surface under `docs/` as release-bound product
documentation, not as optional marketing copy.

Release is blocked until all of the following are true:

- `python3 scripts/tools/sync_release_version.py --version <next-version>` has
  been run
- measured evidence that was not rerun for this release retains its original
  version and carries `<!-- release-version: historical -->`; the version sync
  and consistency gate preserve marked lines instead of relabelling old results
- the work and the release are separate commits, and
  `python3 scripts/testing/check_release_commit_shape.py --range origin/master..HEAD`
  passes: work commits carry the product change, its tests and its docs and bump no
  version, and one `release:` commit carries only the version sweep, the changelog
  section it opens and the release bookkeeping docs
- `python3 scripts/testing/check_release_version_consistency.py` passes
- `python3 scripts/testing/check_release_docs_freshness.py` passes
- `python3 scripts/testing/check_public_release_safety.py` passes, with any
  host-local project names listed only in a gitignored local denylist or in
  `XUUNITY_PUBLIC_SAFETY_DENYLIST`
  Supply one. The gate reports `ok` with `local_denylist_tokens=0` when no denylist
  exists, which reads as "no private tokens found" but means "nothing was looked
  for" — three committed public retros carried a consumer project name and a
  feature codename while it passed. Keep the list in
  `.xuunity-public-safety-denylist` (gitignored, since the list itself names private
  things) with the host's project names, feature codenames, and host identity, and
  check `local_denylist_tokens` in the output is non-zero.
- the freshness audit for the current release has checked `git log
  --oneline --decorate --since=<last-public-doc-refresh>`, the top
  `CHANGELOG.md` release section, `README.md`, `docs/reference/FEATURES.md`,
  `docs/reference/STATUS.md`, `docs/architecture/ROADMAP.md`,
  `docs/operations/SMOKE_TESTS.md`, agent docs, comparison docs, and package
  docs under `packages/com.xuunity.light-mcp/Documentation~/`
- shipped features from the current release are not still described as
  `planned`, `prepared`, `not yet`, or future-only in public entrypoint docs
- current public docs use public-safe validation summaries and do not include
  private project names, host-local paths, local run IDs, screenshots, profile
  names, or host-private evidence labels
- `bash init_xuunity_light_unity_mcp.sh --target both --force` from the source
  checkout installs `run_installed_or_refresh_xuunity_mcp.sh`,
  `run_installed_or_refresh_xuunity_mcp.py`,
  `run_installed_or_refresh_xuunity_mcp.cmd`, and `.source_root`
- client config templates and downstream client docs use the refresh launcher
  for default startup, not plain `run.sh` or `run.cmd`
- a stale neutral helper smoke proves the chain:
  source checkout -> installer -> client config -> refresh launcher -> neutral
  server version; on Windows this must also prove the installed `.source_root`
  marker resolves back to source package metadata from the native refresh
  launcher path
- `docs/index.html` shows the current `softwareVersion`
- `docs/install.html` shows the current Git UPM tag
- `docs/reference/LISTING_KIT.md` shows the current Git UPM tag
- the top `CHANGELOG.md` section describes the release and current package URL
- the changelog and GitHub Release draft follow
  `RELEASE_NOTES_STYLE.md`: developer pain, concrete change, practical benefit,
  exact validation, and every known limitation are stated in language a junior
  Unity developer can follow
- `python3 scripts/testing/check_release_ci_gates.py` reports every required
  CI gate green for the release SHA after the master push

Minimum release closeout sequence:

```bash
python3 scripts/tools/sync_release_version.py --version <next-version>
python3 scripts/testing/check_release_version_consistency.py
python3 scripts/testing/check_release_docs_freshness.py
python3 scripts/testing/check_public_release_safety.py
bash init_xuunity_light_unity_mcp.sh --target both --force
scripts/testing/run_host_python_tests.sh
scripts/testing/run_site_ui_checks.sh
git push origin master
python3 scripts/testing/check_release_ci_gates.py --wait-seconds 1800
git push origin v<next-version>
gh run watch --repo FoxsterDev/xuunity-mcp <release-tag-gate-run-id> --exit-status
gh release create v<next-version> --repo FoxsterDev/xuunity-mcp --verify-tag \
  --title "v<next-version> — <developer outcome>" --notes-file <release-notes.md>
gh release view v<next-version> --repo FoxsterDev/xuunity-mcp \
  --json name,tagName,isDraft,isPrerelease,publishedAt,url
```

The CI gate step is mandatory and sits between the master push and the tag
push: it exits non-zero until every required workflow has a completed,
successful run for the release SHA. Do not push the tag while it is red,
pending, or unable to verify. See `UNITY_PACKAGE_CI.md` for the workflow,
license secrets, and the tag-push `Release Tag Gate` workflow that re-verifies
the same contract in CI.

Required gate workflows must not path-filter their master push trigger. The
gate needs one run per release SHA, so a filtered trigger is unsatisfiable for
any commit outside the filter: no run is created, the gate reads `missing`, and
it polls its whole `--wait-seconds` budget before failing.
`tests/test_ci_workflow_contract.py` enforces this for every gate workflow.

The GitHub Release is a separate required object. Pushing an annotated tag does
not publish the developer-facing release page or its notes. After the tag push,
find the `Release Tag Gate` run for that tag, wait for it to pass, create the
release from the existing tag, and verify that it is published, not a draft or
prerelease. Do not create the release before the tag gate finishes.

Host automation may add private downstream closeout after the public release:
consumer package-pin updates and an external product-site sync. Those steps
must use the exact published tag, preserve unrelated working-tree changes, and
report any project that could not be updated. Do not commit host paths or
consumer names to this public repository.

A workflow that cannot run at all may be suspended through the gate's
`WAIVED_GATES` table rather than deleted from the required set. A waiver is an
explicit, reported evidence gap, not a pass: the run reports
`status=ok_with_waived_gates` with the reason and restore condition, and the
release notes for anything cut under it must say what went unproven. Restore
the gate as soon as the blocker clears. `Unity Package CI` is waived today —
see `UNITY_PACKAGE_CI.md`.

If the site version, install tag, listing metadata, refresh launcher install
output, or client startup docs are stale, do not tag the release and do not
publish the package URL to consumers.

## GitHub Repository UI

Set the repository homepage to:

```text
https://foxsterdev.github.io/xuunity-mcp/
```

Set the GitHub "About" text to:

```text
XUUnity MCP is a lightweight Unity MCP server for safe Unity Editor automation.
```

Add or confirm GitHub topics:

- `xuunity`
- `unity`
- `unity3d`
- `unity-editor`
- `mcp`
- `unity-mcp`
- `mcp-server`
- `ai-agents`
- `gamedev`
- `codex`
- `cursor`
- `claude-code`
- `claude-desktop`
- `windsurf`
- `unity-automation`

## Search Engine Setup

- deploy GitHub Pages through the checked-in `.github/workflows/pages.yml`
  workflow
- if the public URL still returns 404, set GitHub Pages source to GitHub
  Actions in repository settings and rerun the workflow
- verify public pages with:

```bash
python3 scripts/testing/check_public_site.py
```

- submit `https://foxsterdev.github.io/xuunity-mcp/sitemap.xml`
  to Google Search Console
- submit the same sitemap to Bing Webmaster Tools

## Listing / Registry Submission Bundle

Use `../reference/LISTING_KIT.md` as the canonical copy source. Submit in
high-leverage order, not by directory count.

Priority submissions:

- GitHub MCP Registry
- official MCP Registry
- MCP.Directory
- Glama
- PulseMCP
- MCPScout.ai, if an indexable listing or claim flow exists
- Vibehackers MCP Directory, if an indexable listing or claim flow exists
- A2A MCP, if an indexable listing or claim flow exists
- `mcpdir.dev` / MCP Hub, if an indexable listing or claim flow exists
- Machina Directory, if an indexable MCP listing or claim flow exists

Opportunistic submissions:

- MCP Market
- `mcp.so`
- `mcpservers.org`
- MCPlane
- SafeMCP
- MCP Toplist
- Model Context Protocol catalog/downstream pages, derived from official Registry metadata

Skip or defer any directory that cannot expose a public permalink, cannot be
claimed, or does not appear to rank or aggregate credible MCP metadata.

Track submission status in `../reference/LISTING_SUBMISSION_TARGETS.md`.

## External Content Targets

Recommended first wave:

- launch post: `Introducing XUUnity MCP`
- comparison post: `XUUnity MCP vs Unity MCP`
- workflow post: `How to run compile checks and Unity tests through MCP`

Owned drafts are available in `../articles/` and can be adapted for external
community posts.
