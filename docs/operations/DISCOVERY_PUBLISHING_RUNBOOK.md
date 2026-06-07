# Discovery Publishing Runbook

Date: `2026-06-07`
Status: `ready for external publishing`

This runbook implements the updated XUUnity MCP discovery plan. It separates
repo-controlled work from actions that require repository settings, webmaster
accounts, or third-party directory access.

## 1. Publish The Owned Site

The repository now includes a GitHub Pages workflow at:

```text
.github/workflows/pages.yml
```

Expected source:

```text
docs/
```

After the workflow lands on `master`, verify that the public site is live:

```bash
python3 scripts/testing/check_public_site.py
```

If the check returns HTTP 404 for the homepage, open GitHub repository settings
and set Pages to use GitHub Actions as the source, then rerun the workflow.

## 2. Update GitHub Repository Metadata

Set the GitHub repository homepage to:

```text
https://foxsterdev.github.io/xuunity-mcp/
```

Set the About text to:

```text
XUUnity MCP is a lightweight Unity MCP server for safe Unity Editor automation.
```

Confirm topics:

```text
xuunity, unity, unity3d, unity-editor, mcp, unity-mcp, mcp-server, ai-agents, gamedev, codex, cursor, claude-code, claude-desktop, windsurf, unity-automation
```

If GitHub CLI is available and authenticated, the same metadata can be checked
from the command line:

```bash
gh repo view FoxsterDev/xuunity-mcp --json description,homepageUrl,repositoryTopics
```

## 3. Submit Search Indexing

Submit this sitemap to Google Search Console and Bing Webmaster Tools:

```text
https://foxsterdev.github.io/xuunity-mcp/sitemap.xml
```

Request indexing for these pages first:

```text
https://foxsterdev.github.io/xuunity-mcp/
https://foxsterdev.github.io/xuunity-mcp/comparison.html
https://foxsterdev.github.io/xuunity-mcp/alternatives.html
https://foxsterdev.github.io/xuunity-mcp/articles/introducing-xuunity-mcp.html
https://foxsterdev.github.io/xuunity-mcp/articles/xuunity-mcp-vs-unity-mcp.html
https://foxsterdev.github.io/xuunity-mcp/articles/run-unity-compile-checks-and-tests-through-mcp.html
```

## 4. Publish Registry And Directory Listings

Use [LISTING_KIT.md](../reference/LISTING_KIT.md) as the copy source and
[LISTING_SUBMISSION_TARGETS.md](../reference/LISTING_SUBMISSION_TARGETS.md) as
the status tracker.

First-wave priority:

- GitHub MCP Registry
- Official MCP Registry
- MCP.Directory
- MCP Scout
- MCP Market
- mcpservers.org
- MCPlane
- Model Context Protocol catalog pages

## 5. Publish The Content Cluster

Owned article pages are now available under:

```text
docs/articles/
```

Use them as canonical or source drafts for external posts:

- `Introducing XUUnity MCP`
- `XUUnity MCP vs Unity MCP`
- `How to run Unity compile checks and tests through MCP`

When publishing externally, link back to the homepage, comparison page, install
page, and GitHub repository.

## 6. Track Progress

Run public-site checks after every Pages deployment:

```bash
python3 scripts/testing/check_public_site.py
```

Track SERP and listing progress every 2 weeks with:

```text
docs/operations/SERP_TRACKING.md
```
