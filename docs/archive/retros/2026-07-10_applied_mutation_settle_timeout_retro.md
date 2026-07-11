# Scenario Verdict Retro: Applied Mutation Versus Settle Timeout

Date: `2026-07-10`
Status: `host regression passed in unreleased source; live Unity validation pending`

## Finding

A project-defined hook can successfully apply a profile or environment mutation
that triggers a long Unity domain reload. If the immediately following scenario
`project_refresh` times out while waiting for settle, a terminal `failed` status
correctly says the scenario did not finish its proof. It must not also imply the
confirmed hook mutation failed.

## Implemented Contract

For a passed `project_defined_hook` whose payload outcome ends in `*_applied`,
followed immediately by a `project_refresh` step with
`error_code=project_refresh_timeout`, the compact decision verdict now reports:

- `failure_class=applied_mutation_settle_timeout`
- `verdict=inconclusive` and `scenario_status=failed`
- `trust_class=mutation_applied_unsettled`
- `applied_mutation_settle_summary` with separate mutation and settle facts
- `recommended_next_action=verify_editor_settled_before_next_mutation`

The original scenario status and failed refresh step remain visible. This avoids
a false pass while making the precise proven/unproven boundary clear.

## Regression Contract

The host test fixture covers an `environment_applied` hook payload followed by
`project_refresh_timeout`, asserting the mutation and settle fields, compact
first-failure annotation, inconclusive verdict, and non-passing terminal status.
It also guards against overclassification when a non-applied hook outcome or an
intervening successful step precedes the refresh timeout.
