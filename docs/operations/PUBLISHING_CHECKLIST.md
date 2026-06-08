# Publishing Checklist

Date: `2026-06-07`
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
- `python3 scripts/testing/check_release_version_consistency.py` passes
- `docs/index.html` shows the current `softwareVersion`
- `docs/install.html` shows the current Git UPM tag
- `docs/reference/LISTING_KIT.md` shows the current Git UPM tag
- the top `CHANGELOG.md` section describes the release and current package URL

Minimum release closeout sequence:

```bash
python3 scripts/tools/sync_release_version.py --version <next-version>
python3 scripts/testing/check_release_version_consistency.py
scripts/testing/run_host_python_tests.sh
git push origin master
git push origin v<next-version>
```

If the site version, install tag, or listing metadata is stale, do not tag the
release and do not publish the package URL to consumers.

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
