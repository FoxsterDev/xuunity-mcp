# MCP Directory UX References

Date: `2026-06-07`
Status: `reference for future public-site UX/UI redesign`

Use this document as public-safe product research for improving the XUUnity MCP
site and directory submission materials. It summarizes external MCP discovery
surfaces and community signals without copying private project details into
public documentation.

## Research Sources

Primary public directory and registry references:

- [Glama](https://glama.ai/)
- [MCP.Directory](https://mcp.directory/)
- [MCP.Directory submit page](https://mcp.directory/submit)
- [PulseMCP server directory](https://www.pulsemcp.com/servers)
- [SafeMCP](https://safemcp.info/)
- [MCPlane](https://mcplane.com/)
- [MCP Toplist](https://mcptoplist.com/)
- [mcp.so](https://mcp.so/)
- [mcpservers.org](https://mcpservers.org/)
- [MCP Market](https://mcpmarket.com/en/categories)
- [Official MCP Registry quickstart](https://modelcontextprotocol.io/registry/quickstart)
- [Official MCP Registry about page](https://modelcontextprotocol.io/registry/about)

User-signal references:

- [Would you use another MCP server directory?](https://www.reddit.com/r/mcp/comments/1ttk9y5/would_you_use_another_mcp_server_directory_or_is/)
- [I built the largest free directory of MCP servers](https://www.reddit.com/r/mcp/comments/1tm7duq/i_built_the_largest_free_directory_of_mcp_servers/)
- [9 directories, 3 weeks, 1 person, $500 budget](https://www.reddit.com/r/mcp/comments/1sy0vmg/9_directories_3_weeks_1_person_500_budget_what_i/)

## What Users Seem To Value

These are recurring signals from public directory UX and user discussion. Treat
them as practical product heuristics, not formal market research.

- Maintenance signals matter more than raw listing count: last update, release
  freshness, issue response, README freshness, version history, and working
  install paths.
- Source trust matters: verified GitHub source, official/provider/community
  classification, license, stars, and clear maintainer identity.
- Install friction is a conversion killer: users want copy-ready config snippets
  for Claude Desktop, Claude Code, Cursor, VS Code/Copilot, Codex, Windsurf, and
  similar clients.
- Compatibility needs to be visible before the user clicks deep into docs:
  supported clients, transport, runtime, package manager, auth/API-key
  requirements, and local-vs-remote mode.
- Evaluation needs proof, not only marketing: users look for health checks,
  safety notes, scores, tool schemas, quality claims, and concrete examples.
- Discovery benefits from task-level search: users often search for a capability
  like `run tests`, `query Postgres`, or `browser automation`, not only a server
  name.
- Too many directories feel duplicative; the sites that stand out give either
  deeper verification, easier install, better ranking, or a live test/inspector
  path.

## High-Leverage Discovery Shortlist

For the `unity mcp` top-5 search goal, treat directory submissions as an SEO and
answer-engine distribution problem, not a badge collection exercise.

Highest leverage:

- Owned surfaces: GitHub repo metadata, GitHub Pages homepage, sitemap,
  comparison pages, and article cluster.
- Canonical registries: official MCP Registry and GitHub MCP Registry.
- High-signal MCP directories: MCP.Directory, Glama, and PulseMCP.
- Current Unity MCP SERP surfaces: MCPScout.ai, Vibehackers MCP Directory, and
  mcpdir.dev / MCP Hub if XUUnity MCP can get an indexable server permalink.

Lower leverage unless the submit path is fast:

- MCP Market, `mcp.so`, `mcpservers.org`, MCPlane, SafeMCP, and MCP Toplist.
- Any scanner-derived surface that cannot be claimed or does not expose a stable
  public listing URL.

Use MCPlane and similar pages as UX references for compact capability cards and
badges, but do not treat them as priority submissions unless current SERP checks
show they rank for Unity MCP queries.

## Best UX Patterns To Reuse

### Glama

Useful patterns:

- First viewport combines scale, trust, search, and a clear explanation of how
  the platform differs from the official registry.
- Strong evaluator promise: server quality/safety scores, maintainer
  verification, continuous rebuilds, and browser-based testing before install.
- Tool-level search and inspector positioning make the page feel operational,
  not only editorial.

XUUnity translation:

- Put "first trustworthy proof" next to the install CTA: setup-plan review,
  validate-setup, ensure-ready, compile matrix, EditMode, and PlayMode.
- Add a future "try before adopting" module only when a real demo video or
  reproducible public sandbox exists.
- Make tool-surface safety visible: editor-only default, validation-first tools,
  capability-gated optional features.

### MCP.Directory

Useful patterns:

- Clear public stats, popular/recent/installed sections, category navigation,
  client one-click install framing, and a lightweight submit flow.
- Submit page explains what metadata is auto-pulled from GitHub and what happens
  after submission.

XUUnity translation:

- Keep directory submission copy aligned with GitHub README, homepage, install
  page, and `mcp-server.json`.
- Add short directory-ready feature bullets that map to likely auto-detected
  metadata: tools, license, language/runtime, README quality, and install config.
- Ensure the homepage gives crawlers and directory maintainers enough text to
  identify `unity`, `game development`, `developer tools`, `testing`, and
  `automation`.

### PulseMCP

Useful patterns:

- Dense browsable directory with trending topics, classification filters,
  popularity estimates, release dates, and broad client framing.
- Unity appears as a discoverable trend/category, which makes it important for
  the XUUnity page to carry explicit Unity and game-development language.

XUUnity translation:

- Prioritize "Unity" and "game development" category language in every listing.
- Include release date/version freshness and public release evidence in the
  submission copy where the directory allows it.

### SafeMCP

Useful patterns:

- Minimal, fast directory UI centered on verified count, score distribution,
  categories, need-API-key percentage, and top picks.
- Honest disclaimer that the score is not a security audit.

XUUnity translation:

- Use concise safety claims and caveats. "Safe setup flow" should always mean
  reviewed setup-plan plus validation-first editor automation, not a blanket
  security guarantee.
- Keep "no API key required" and "local-first stdio" highly visible where true.

### MCPlane

Useful patterns:

- Marketplace-style framing with categories, most-starred list, verified labels,
  "well documented" badges, capability counts, complexity, server type, and AI
  analyzer metadata.
- Detail cards surface value proposition before long README content.

XUUnity translation:

- Add a directory-friendly "At a glance" block in future redesigns: transport,
  package URL, source repo, clients, Unity versions, tools, footprint, and
  safety model.
- Prefer compact badges for "Official? no", "Open source", "MIT", "stdio",
  "local-first", "editor-only", "testing", and "game development".

### MCP Toplist

Useful patterns:

- Ranking method is explicit: score, stars, release activity, version count,
  listing age, and registry coverage.
- It tracks multiple registries and exposes the idea that a server can gain
  trust by appearing across several credible surfaces.

XUUnity translation:

- Track listing coverage as a distribution metric, not only search ranking.
- Add published listing URLs back into `LISTING_SUBMISSION_TARGETS.md` and
  `SERP_TRACKING.md` after each acceptance.

### mcp.so, mcpservers.org, MCP Market

Useful patterns:

- Simple marketplace/category pages with submit links and broad category tags.
- These surfaces often favor short descriptions, featured lists, and category
  density over deep proof.

XUUnity translation:

- Keep a short, exact, repeatable listing description.
- Prepare one compact config snippet and one homepage URL; do not rely on each
  directory reading the full README correctly.

## Recommended XUUnity Site Redesign Moves

- Replace some current long-form hero density with a faster decision surface:
  "What it is", "Who it is for", "Proof path", "Install", "Compare".
- Add an "At a glance" panel near the first viewport:
  `stdio`, `local-first`, `MIT`, `Unity Editor`, `Git UPM`, `Codex/Cursor/Claude/Windsurf/Rider`, `v0.3.21`.
- Add a "Proof before install" strip:
  `setup-plan`, `validate-setup`, `ensure-ready`, `compile matrix`, `EditMode`, `PlayMode`.
- Make maintenance/freshness visible:
  current version, latest public site check date, release consistency check, and
  last validation summary.
- Add a compact "What tools are exposed?" section using capability groups:
  setup, readiness, status, compile, tests, console, scene assertions,
  screenshots, recovery.
- Add a copy-ready client config area with tabs or sections for Codex, Cursor,
  Claude Code, Claude Desktop, Windsurf, and Rider.
- Keep safety language precise:
  reviewed setup mutation, editor-only base package, capability gating, and
  validation-heavy workflow.
- Do not claim formal security certification unless a real third-party audit or
  reproducible public scanner result exists.

## Submission Copy Priorities

When a directory gives only a few fields, prioritize:

1. Name: `XUUnity MCP`
2. Homepage: `https://foxsterdev.github.io/xuunity-mcp/`
3. Repository: `https://github.com/FoxsterDev/xuunity-mcp`
4. One-line description:
   `XUUnity MCP is a lightweight Unity MCP server for safe Unity Editor automation.`
5. Category: `Developer Tools`, `Game Development`, `Testing`, `Automation`, or
   closest available equivalents.
6. Tags:
   `unity`, `mcp`, `unity-mcp`, `testing`, `automation`, `editor`, `safe`,
   `stdio`, `local-first`.
7. Proof phrase:
   `Validation-first workflow for setup review, compile checks, EditMode tests, PlayMode tests, scene assertions, and screenshots.`

## Open Follow-Ups

- Submit to the official MCP Registry first once the registry-specific
  `server.json` flow is confirmed for this repo.
- Re-check whether GitHub MCP Registry has a direct public submission flow or is
  populated from official/partner registry metadata.
- Use accepted directory permalinks as future UI references for how external
  platforms summarize XUUnity MCP.
- Record a real demo video before adding a video claim to the homepage.
