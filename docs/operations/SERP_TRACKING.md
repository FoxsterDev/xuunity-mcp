# SERP Tracking

Date: `2026-06-07`
Status: `operational checklist`

Track these query groups every 2 weeks after the Pages site and listings go
live.

## Brand Queries

- `xuunity mcp`
- `xuunity unity mcp`
- `xuunity light unity mcp`

## Niche Queries

- `safe unity mcp`
- `lightweight unity mcp`
- `unity mcp testing`
- `unity mcp compile validation`

## Head Queries

- `unity mcp`
- `best unity mcp`
- `unity mcp server`

## Surfaces To Watch

- GitHub repo result
- GitHub Pages homepage
- comparison page
- alternatives page
- articles hub
- launch, comparison, and workflow article pages
- client guides hub
- registry and directory listings

## Success Checks

- brand query returns at least one owned surface in the visible results
- niche query returns the homepage or comparison page
- head-term query begins surfacing at least one owned page plus at least one
  listing page

## Public Site Smoke Check

After every Pages deployment, run:

```bash
python3 scripts/testing/check_public_site.py
```

This check should pass before submitting new indexing requests or directory
updates.
