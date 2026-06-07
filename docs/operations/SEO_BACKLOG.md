# XUUnity MCP SEO / Discovery Backlog

Date: `2026-06-07`
Status: `active`
Owner: `FoxsterDev`

This backlog updates the original plan for getting
`FoxsterDev/xuunity-mcp` visible for:

- `xuunity mcp`
- `Unity MCP`
- niche terms such as `safe unity mcp`, `lightweight unity mcp`,
  `unity mcp testing`, and `unity compile validation mcp`

Use this file as the live execution tracker: what is already done, what still
needs manual work, and what should happen next.

## Current Position

- Product brand in public-facing surfaces: `XUUnity MCP`
- Full technical package name: `XUUnity Light Unity MCP`
- Current site implementation exists inside this repo under `docs/`
- Current repo-local canonical site path targets:
  `https://foxsterdev.github.io/xuunity-mcp/`
- Current GitHub repo slug:
  `FoxsterDev/xuunity-mcp`

Important:

- The current code repo has already been aligned to the public slug
  `xuunity-mcp`.
- The next step is publishing and indexing, not repository-name strategy.

## What Has Been Done

### Repo metadata and discovery signals

- [x] `README.md` updated to lead with `XUUnity MCP`
- [x] `README.md` now reinforces `lightweight`, `safe`, and
  `validation-first Unity MCP` positioning
- [x] `llms.txt` updated with brand and search keyword variants
- [x] `mcp-server.json` updated with stronger keywords and new homepage target
- [x] GitHub repo slug references updated from
  `FoxsterDev/xuunity-light-unity-mcp` to `FoxsterDev/xuunity-mcp`
- [x] Pages/site canonical references updated from
  `/xuunity-light-unity-mcp/` to `/xuunity-mcp/`
- [x] `docs/reference/DISCOVERY.md` updated for `xuunity mcp` and niche terms
- [x] `docs/reference/COMPARISON.md` updated to use `XUUnity MCP` short brand

### GitHub Pages-ready site surface

- [x] `docs/index.html` created as the main landing page
- [x] `docs/install.html` created
- [x] `docs/comparison.html` created
- [x] `docs/use-cases.html` created
- [x] `docs/alternatives.html` created
- [x] `docs/what-is-unity-mcp.html` created
- [x] `docs/xuunity-vs-coplaydev-unity-mcp.html` created
- [x] `docs/clients/index.html` created
- [x] `docs/articles/index.html` created
- [x] `docs/articles/introducing-xuunity-mcp.html` created
- [x] `docs/articles/xuunity-mcp-vs-unity-mcp.html` created
- [x] `docs/articles/run-unity-compile-checks-and-tests-through-mcp.html` created
- [x] `docs/robots.txt` created
- [x] `docs/sitemap.xml` created
- [x] `docs/.nojekyll` created
- [x] GitHub Actions Pages workflow added at `.github/workflows/pages.yml`

### Proof assets and conversion assets

- [x] benchmark-like validation section added to the homepage
- [x] architecture diagram added:
  `docs/assets/xuunity-mcp-architecture.svg`
- [x] supported clients table added to the homepage
- [x] supported Unity versions table added to the homepage
- [x] feature matrix against other Unity MCP tools added to the homepage
- [x] demo walkthrough section with transcript/indexable summary added
- [x] premium engineering-oriented styling added:
  `docs/assets/site.css`
- [x] storyboard poster for the demo added:
  `docs/assets/xuunity-demo-storyboard.svg`

### Operational follow-up docs

- [x] listing metadata bundle created:
  `docs/reference/LISTING_KIT.md`
- [x] listing target tracker created:
  `docs/reference/LISTING_SUBMISSION_TARGETS.md`
- [x] manual publishing checklist created:
  `docs/operations/PUBLISHING_CHECKLIST.md`
- [x] discovery publishing runbook created:
  `docs/operations/DISCOVERY_PUBLISHING_RUNBOOK.md`
- [x] public site verification utility created:
  `scripts/testing/check_public_site.py`
- [x] search tracking checklist created:
  `docs/operations/SERP_TRACKING.md`
- [x] this live execution backlog created:
  `docs/operations/SEO_BACKLOG.md`

## What Is Not Done Yet

### GitHub UI / publishing setup

- [x] Add repository workflow for GitHub Pages publishing from `docs/`
- [ ] Enable or verify GitHub Pages publishing for the site in GitHub settings
- [ ] Update GitHub repo `About` text manually in the GitHub UI
- [ ] Update GitHub repo homepage manually in the GitHub UI
- [ ] Add GitHub topic `xuunity` manually if it is still missing

### Search engine setup

- [ ] Submit sitemap to Google Search Console
- [ ] Submit sitemap to Bing Webmaster Tools
- [ ] Request indexing for homepage
- [ ] Request indexing for comparison page
- [ ] Request indexing for alternatives page

### Directory / registry distribution

- [ ] Publish/update GitHub MCP Registry listing
- [ ] Publish/update official MCP Registry listing
- [ ] Publish/update MCP Scout listing
- [ ] Publish/update MCP Market listing
- [ ] Publish/update `mcpservers.org` listing
- [ ] Publish/update other relevant MCP directory pages

### External authority signals

- [x] Create owned launch article: `Introducing XUUnity MCP`
- [x] Create owned comparison article: `XUUnity MCP vs Unity MCP`
- [x] Create owned tutorial article: `How to run compile checks and Unity tests through MCP`
- [ ] Publish launch post externally: `Introducing XUUnity MCP`
- [ ] Publish comparison post externally: `XUUnity MCP vs Unity MCP`
- [ ] Publish tutorial post externally: `How to run compile checks and Unity tests through MCP`
- [ ] Add links from personal site / portfolio
- [ ] Add links from GitHub profile / pinned repo / public profiles
- [ ] Add links from relevant MCP or Unity community resources

### Remaining product-proof upgrades

- [ ] Replace storyboard-only demo with a real short video asset (`.mp4` or `.webm`)
- [x] Add real-video production plan and caption script:
  `docs/operations/DEMO_VIDEO_PRODUCTION.md`
- [ ] Add one real end-to-end case study or engineering usage example
- [ ] Add social proof if real users/projects exist and can be named publicly

## Recommended Next Actions

### Highest-impact next steps

1. Publish the site publicly through GitHub Pages.
2. Run `python3 scripts/testing/check_public_site.py` after the Pages workflow deploys.
3. Update GitHub UI metadata:
   - About
   - Homepage
   - Topics
4. Submit sitemap to Google and Bing.
5. Push the first wave of directory/registry listings using `LISTING_KIT.md`.

### Best next content moves

1. Create a real demo video from the existing storyboard flow.
2. Publish one launch post and one comparison post.
3. Add one detailed workflow article for compile/tests/scene validation.

## Suggested Execution Order

### Phase 1: publish what already exists

- [ ] push/commit current repo changes
- [x] add GitHub Pages workflow
- [ ] enable GitHub Pages or set Pages source to GitHub Actions
- [ ] verify public site loads
- [ ] verify `robots.txt` and `sitemap.xml` are reachable

### Phase 2: connect search/discovery

- [ ] update GitHub UI metadata
- [ ] submit sitemap
- [ ] request indexing
- [ ] begin query tracking from `SERP_TRACKING.md`

### Phase 3: widen discovery

- [ ] submit registry and directory listings
- [ ] publish launch/comparison/tutorial content
- [ ] start collecting relevant backlinks

### Phase 4: improve conversion

- [ ] ship real demo video
- [ ] add real engineering proof/case study
- [ ] add stronger public trust signals as they become available

## Progress Summary

- Strategy and positioning: `done`
- Repo-level discovery metadata: `done`
- Site structure and landing pages: `done`
- Owned article cluster: `done`
- Proof assets on the homepage: `mostly done`
- Real video proof: `not done`
- GitHub Pages workflow: `done`
- GitHub UI publishing actions: `not done`
- Search engine submission: `not done`
- External listings and backlinks: `not done`

Overall execution state: `about 70% of the repo/site work is done, but the
highest-impact external distribution steps are still ahead`
