# Listing Submission Targets

Date: `2026-06-07`
Status: `submission tracker`

Use this tracker with [LISTING_KIT.md](LISTING_KIT.md). Each listing should use
the same canonical brand, homepage, short description, full description,
keywords, tags, and proof assets.

## Canonical Submission Copy

- Name: `XUUnity MCP`
- Full technical name: `XUUnity Light Unity MCP`
- Repository: <https://github.com/FoxsterDev/xuunity-mcp>
- Homepage: <https://foxsterdev.github.io/xuunity-mcp/>
- Description: `XUUnity MCP is a lightweight Unity MCP server for safe Unity Editor automation.`
- Tags: `unity`, `mcp`, `unity-mcp`, `testing`, `automation`, `editor`, `safe`

## SEO / AI Recommendation Priority

The goal is not maximum directory count. The goal is to maximize the chance of
appearing in the top results for `unity mcp` and being picked up by current MCP
aggregators, AI assistant catalogs, and answer engines.

Scoring uses a public, qualitative 1-5 scale. It is not a paid Moz/Ahrefs
domain-authority score.

- Indexability: stable public permalink, crawlable body text, category pages,
  sitemap/SEO shape, and current evidence of indexed Unity MCP pages.
- Authority/trust: official MCP/GitHub ownership, known MCP ecosystem role,
  source verification, and visible quality/review process.
- AI recommendation potential: registry API/import path, tool/schema metadata,
  client install configs, inspector/safety metadata, and likelihood that
  assistant catalogs or answer engines reuse the surface.

Do not spend high effort on a directory only because it has attractive UI. For
this search goal, indexability, canonical metadata import, and existing Unity
MCP query visibility matter more than visual polish.

## Leverage-Ranked Targets

| Rank | Target | Priority | Status | Indexability | Authority / trust | AI rec potential | Score | Decision |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | GitHub MCP Registry / <https://github.com/mcp> | P0 | Verify direct-submit or registry-import path | 5 | 5 | 5 | 15 | Highest external leverage if XUUnity can be listed; GitHub domain plus AI-developer workflow proximity. |
| 2 | GitHub repo + GitHub Pages | P0 | Repo/Page live; GitHub UI/search indexing still manual | 5 | 5 | 4 | 14 | Keep as the owned baseline: repo About/topics, homepage, sitemap, articles, and request indexing. |
| 3 | Official MCP Registry / <https://modelcontextprotocol.io/registry/quickstart> | P0 | Not submitted | 3 | 5 | 5 | 13 | Publish canonical metadata first; downstream aggregators and registries can import it. |
| 4 | MCP.Directory / <https://mcp.directory/submit> | P1 | Not submitted | 5 | 4 | 4 | 13 | Submit early; auto-pulls GitHub metadata/tools and generates client install configs. |
| 5 | Glama / <https://glama.ai/mcp/servers> | P1 | Not submitted | 5 | 4 | 4 | 13 | Add or claim; strong tool/schema/search metadata and MCP API/inspector adjacency. |
| 6 | PulseMCP / <https://www.pulsemcp.com/servers> | P1 | Not submitted | 4 | 4 | 4 | 12 | Submit for Unity category, recommended sorting, freshness, and classification surfaces. |
| 7 | MCPScout.ai / <https://www.mcpscout.ai/> | P1 | Verify/claim flow | 5 | 3 | 4 | 12 | Claim only if a public XUUnity permalink can exist; useful for safety notes and similar-server graph. |
| 8 | Vibehackers MCP Directory / <https://vibehackers.io/mcp> | P1 | Verify/claim flow | 5 | 3 | 3 | 11 | Worth it if claimable; current Unity pages expose one-prompt install/config UX. |
| 9 | A2A MCP / <https://a2a-mcp.org/> | P2 | Verify/submit flow | 4 | 3 | 3 | 10 | SERP-visible for Unity MCP and has a submit path; use only public-safe listing copy. |
| 10 | `mcpdir.dev` / MCP Hub / <https://mcpdir.dev/> | P2 | Verify/claim flow | 4 | 3 | 3 | 10 | Claim if possible; current Unity pages are indexable and have source/validation fields. |
| 11 | Machina Directory / <https://machina.directory/> | P2 | Verify MCP submit path | 4 | 3 | 2 | 9 | SERP-visible install page, but submit/claim flow appears less direct; opportunistic after P1. |
| 12 | `mcp.so` / <https://mcp.so/submit> | P2 | Not submitted | 3 | 2 | 3 | 8 | Fast submit form with config field; do if it takes minutes, not custom effort. |
| 13 | `mcpservers.org` / <https://mcpservers.org/> | P2 | Not submitted | 3 | 2 | 3 | 8 | Submit if public permalink is created; broad directory value, lower authority signal. |
| 14 | MCP Market / <https://mcpmarket.com/en/categories> | P3 | Not submitted | 3 | 2 | 2 | 7 | Opportunistic marketplace/category listing only. |
| 15 | SafeMCP / <https://safemcp.info/> | P3 | Verify scanner/claim flow | 3 | 2 | 2 | 7 | Useful if scanner-derived safety metadata appears, but not a primary SEO target. |
| 16 | MCPlane / <https://mcplane.com/> | P3 | Not submitted | 2 | 2 | 2 | 6 | Keep as UX reference; submit only if quick and indexable. |
| 17 | MCP Toplist / <https://mcptoplist.com/> | P3 | Verify derived listing flow | 2 | 2 | 2 | 6 | Likely derived/ranking surface; wait for canonical registries first. |

Recommended execution order:

1. Update owned GitHub/Page indexing surfaces.
2. Publish official MCP Registry metadata.
3. Verify whether GitHub MCP Registry imports from official Registry or has a
   direct listing route.
4. Submit MCP.Directory, Glama, and PulseMCP.
5. Claim only the current `unity mcp` SERP surfaces that expose stable public
   permalinks: MCPScout.ai, Vibehackers, A2A MCP, `mcpdir.dev`, and Machina.
6. Use the lower-score directories only for fast, low-maintenance submissions.

Model Context Protocol catalog/downstream pages are tracked as a derived benefit
of official Registry publication, not as a separate manual submission target.

## Submission Rules

- Always use `https://foxsterdev.github.io/xuunity-mcp/` as the homepage.
- Always use `https://github.com/FoxsterDev/xuunity-mcp` as the source repo.
- Keep the short positioning phrase identical across listings.
- Prefer categories that include both `Unity` and `development tools` when a
  directory allows multiple categories.
- After publication, add the live listing URL to this file and to the tracking
  notes in [SERP_TRACKING.md](../operations/SERP_TRACKING.md).

## Per-Target Preparation Notes

### Official MCP Registry

- Confirm the registry-specific `server.json` schema and namespace strategy
  before publishing.
- Likely namespace candidate: `io.github.foxsterdev/xuunity-mcp` or the exact
  case-preserving GitHub namespace required by the official publisher.
- Current repo discovery metadata exists in `mcp-server.json`, but do not assume
  that file is a valid official Registry `server.json` without schema
  validation.
- Search check on `2026-06-07` returned no official registry entry for
  `xuunity`.

### MCP.Directory

- Submit repository URL first.
- The submit page says it can auto-detect GitHub metadata, tools, README,
  language, license, and install configurations.
- Optional fields to provide manually:
  short description, npm package if one exists, PyPI package if one exists, and
  notification email.

### Glama

- Prioritize tool/schema clarity and safety language because Glama emphasizes
  quality, safety, tool-level search, and browser inspection.
- Use the same homepage and GitHub source; verify whether XUUnity is already
  indexed before requesting manual addition.

### PulseMCP

- Use Unity, game development, developer tools, testing, and automation language
  prominently.
- PulseMCP surfaces classifications, release dates, popularity estimates, and
  trending topics, so version freshness and current homepage should be visible.

### MCPScout.ai, Vibehackers, A2A MCP, mcpdir.dev, Machina

- Treat these as SERP-driven targets, not generic directories.
- Prioritize them only if XUUnity MCP can get an indexable server permalink or
  a visible claim/update flow.
- Current tracking should use `https://www.mcpscout.ai/` for the directory
  surface. Do not track `https://mcpscout.dev/` as the SEO target unless that
  product later exposes a relevant public MCP listing page.
- A2A MCP currently exposes an indexable Unity MCP entry and a submit route, so
  it belongs in the SERP-visible P2 bucket rather than the generic directory
  bucket.
- Machina currently exposes an indexable Unity MCP install page, but its MCP
  submit/claim route needs verification before spending custom effort.
- For these surfaces, the acceptance criterion is a stable public XUUnity MCP
  permalink, not merely a temporary search result or feed entry.
- Use the one-prompt setup idea in public-safe form:
  `Set up XUUnity MCP from the repository README into /path/to/UnityProject,
  run EditMode tests there, and print the results here.`

### MCP Market, mcp.so, mcpservers.org

- Prepare a compact server config/install snippet before submission.
- Prefer the one-line description from [LISTING_KIT.md](LISTING_KIT.md).
- Add categories in this order when supported:
  `Game Development`, `Developer Tools`, `Testing`, `Automation`.

### MCPlane

- Prepare a compact server config/install snippet before submission.
- Prefer the one-line description from [LISTING_KIT.md](LISTING_KIT.md).
- Add categories in this order when supported:
  `Game Development`, `Developer Tools`, `Testing`, `Automation`.
- Keep this opportunistic for now. It remains a useful UX reference, but it is
  not a top manual target for the `unity mcp` top-5 search goal unless current
  SERP checks show it ranking for Unity MCP queries.

### SafeMCP, MCP Toplist

- Treat these as verification/discovery surfaces until a clear direct submission
  flow is confirmed.
- If the surface is scanner-derived, first make sure the official Registry,
  GitHub README, homepage, and `mcp-server.json` metadata are coherent.
