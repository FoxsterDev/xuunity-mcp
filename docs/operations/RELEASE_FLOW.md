# Unified release flow

This is the project entry point for manual and scheduled releases. Read this
whole file, `PUBLISHING_CHECKLIST.md`, `RELEASE_NOTES_STYLE.md`, and
`skills/release_ci_guardrails/SKILL.md` from the repository root before acting.
These documents define gates, not permission to push or publish.

## Two entry modes

- **Release existing changes**: inspect existing commits and working-tree changes,
  freeze the reviewed scope, and release that work. Do not select a retro or add
  a new feature. Necessary validation fixes must remain within the reviewed scope;
  ask before expanding it. Preserve unrelated staged, unstaged and untracked files.
- **Retro to release**: select and implement one improvement using the host's
  grooming rules, then enter the same release-existing-changes flow.

Manual request:

> Release the existing reviewed XUUnity MCP changes using RELEASE_FLOW.md and
> the configured private closeout profile. Include consumer rollout, the external
> product website and LinkedIn. Do not add new development. Confirm the scope and
> applicable publication permissions before external actions.

Planning, resuming and publishing are distinct operations. A request to implement
or dry-run this workflow does not authorize a real release. If the private
closeout profile is unavailable, report that limitation; never invent paths or
silently claim the full release is complete.

Resolve the owner-configured private profile with
`git config --local --get xuunity.releaseProfile` from this repository. Read the
returned file in full. This local Git setting contains a path, not credentials;
the actual rules remain in the owner's private repository. A fresh clone needs
its own owner-supplied profile binding. Do not guess missing host paths.

## Ordered stages

1. **Preparation**: inspect Git status/diff, branch and remotes, latest public tag
   and release, Unreleased notes, and source scope. Resolve dirty target conflicts.
   Choose an unused version from verified remote state, not a hard-coded number.
   Record the baseline commit, reviewed paths, validation requirements and authority.
2. **Validation**: use the existing publishing checklist and release skill. Keep
   work commits separate from the version-only release commit; validate the final
   release tree. Record exact pass, skip, waiver and missing-evidence results.
   Local passes do not replace remote CI. Freeze the release commit SHA.
3. **GitHub release**: with explicit applicable authority, push the reviewed
   commits, wait for commit CI gates, create/push the annotated tag, wait for the
   tag gate, then publish and verify the GitHub Release. Bind tag, SHA and notes.
   An existing tag is reconciled, never moved or recreated. A tag alone is not a
   published release. A retry must inspect remote state before any write.
4. **Consumer rollout**: follow `CONSUMER_RELEASE_ROLLOUT.md` and the private
   profile's exact inventory. Preflight, canary, serial fan-out, evidence and
   process ownership are mandatory. Leave consumer changes uncommitted/unpushed.
5. **External product website**: use the website repository's current update,
   publishing and release protocols. Verify production version, immutable release
   link, HTTP, canonical, robots and sitemap after its approved deployment.
   GitHub Pages documentation in this repository is updated before the SDK tag;
   the external product website is updated after the verified GitHub Release.
   They are different surfaces, not conflicting release order requirements.
6. **LinkedIn closeout**: use the configured private channel's existing template,
   permissions, cadence and publication ledger. One useful release outcome by
   default, two maximum. Verify the public release and website first. A verified
   native scheduled post is `scheduled`, not `published`; cadence holds and browser
   access failures remain visible. Never send twice after an uncertain attempt.

## Resume and completion

The private profile owns a per-version coordination record. Evidence remains in
the owning lanes: consumer ledger, website evidence, and shared publication
ledger. The coordination record references them, never creates a second social
queue. Recheck evidence against the exact version/SHA on every resume.

Post-release consumer and website lanes may progress independently; a consumer
failure must remain reported and must not be portrayed as successful validation
in public copy. LinkedIn requires both GitHub and production website proof.
Never roll back or rewrite a public release to hide a downstream failure.

Report each lane separately and one overall result: `blocked_before_release`,
`downstream_partial`, `delivery_scheduled`, or `complete`. Only verified public
delivery closes LinkedIn; a scheduled delivery remains pending reconciliation.
Include exact blockers, artifact references and the next safe action. Do not
claim a scheduled task ran, a deployment succeeded or a post is live from local
files alone.
