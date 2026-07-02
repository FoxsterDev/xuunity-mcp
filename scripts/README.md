# Scripts

Developer and operator utilities live here so the repository root stays focused
on public setup entrypoints.

## Sections

- [testing](testing/) - host tests, multi-project runners, and Unity version matrix
- [tools](tools/) - local helper utilities used by wrappers and smoke lanes

## Release Version Helpers

Use the package manifest as the version source of truth:

```bash
python3 scripts/tools/sync_release_version.py --version 0.3.17
python3 scripts/testing/check_release_version_consistency.py
python3 scripts/testing/check_release_docs_freshness.py
scripts/testing/run_host_python_tests.sh
```

`sync_release_version.py` updates package metadata, server metadata, package
manifest templates, the GitHub Pages site surfaces, listing metadata, and
current release-facing docs without rewriting historical changelog or migration
references. The host test suite runs `check_release_version_consistency.py` and
`check_release_docs_freshness.py` first so stale current-version references and
known stale public-doc claims fail before tagging. Treat the public site and
public entrypoint docs as part of the release surface: if they are stale, the
MCP release is not ready to tag.

Root-level setup wrappers remain at the repo root:

- `init_xuunity_light_unity_mcp.sh`
- `xuunity_light_unity_mcp.sh`
