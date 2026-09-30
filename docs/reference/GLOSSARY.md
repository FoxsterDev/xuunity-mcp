# Glossary

Date: `2026-05-23`
Status: `current for v0.3.82`

## XUUnity

XUUnity is the surrounding AI-assisted Unity workflow system used by this project. The MCP service can also be consumed as a standalone Unity Editor automation layer.

## MCP

MCP means Model Context Protocol. It lets AI clients call structured tools exposed by a local or remote server.

## Host-Side MCP Server

The host-side server is the local process that speaks MCP to AI clients and routes requests to a Unity project.

## Unity Package

The Unity package is `com.xuunity.light-mcp`. It contains the editor-side bridge and editor-only operations used by the host-side MCP server.

Current production Git UPM path:

```text
https://github.com/FoxsterDev/xuunity-mcp.git?path=/packages/com.xuunity.light-mcp#v0.3.82
```

## Git UPM

Git UPM is Unity Package Manager installing a package directly from a Git URL.
It is the current production install route for this package until OpenUPM is
published.

## OpenUPM

OpenUPM is a public Unity package registry. XUUnity Light Unity MCP has a
registry-native package path, but the documented install route is still Git UPM
until an OpenUPM package page exists.

## devmode

`devmode` points a consumer Unity project at the local package folder for MCP
package development.

## prodmode

`prodmode` points a consumer Unity project at a published Git package source.
It pins the package to the published release tag that matches the package
version so release-bound projects do not depend on local-only package changes.

## Optional Capability

An MCP feature that may be `supported`, `unsupported`,
`disabled_missing_dependency`, `disabled_dependency_too_old`, `degraded`, or
`error` without making the core MCP health fail.

## Test Framework Capability

The optional EditMode and PlayMode test surface backed by
`com.unity.test-framework`. Unity enables it through asmdef Version Defines
when `XUUNITY_LIGHT_MCP_TESTS_CAPABILITY` is available.

## BridgeRegistry

BridgeRegistry is the local routing layer used to map MCP requests to the correct Unity project/editor instance on the same host.

## ProjectContext

ProjectContext is the host-side state for a single Unity project, including project paths, bridge state, editor session evidence, and request routing metadata.

## Same-Host Editor Automation

Same-host automation means the AI client, MCP server, and Unity Editor run on the same trusted machine or CI host.

## Request Journal

The request journal is the per-project record under
`Library/XUUnityLightMcp/journal/requests/` used to recover final request status
after Unity reloads, transport churn, or wrapper timeouts.

## Scenario

A scenario is a bounded JSON workflow that asks Unity MCP to perform ordered validation steps such as refresh, compile, Play Mode, scene checks, screenshots, or project-defined hooks.

## Trust, Outcome and Warning Vocabulary

Every value this system publishes in a trust, outcome, warning or gap field.
A value not in this table must not be published, and a new value is added here
in the same change that emits it.

### `result_trust_class`

| Value | Produced by | Read by |
| --- | --- | --- |
| `editor_truth_confirmed` | the editor's point-of-use liveness sampler, mirrored by the host for lifecycle-recovered Play Mode payloads | scenario liveness summary, scenario decision verdict |
| `playmode_advancing_confirmed` | the same pair | the same |
| `playmode_throttled` | the same pair, plus the scenario decision verdict | the same |
| `playmode_liveness_unproven` | the same pair, plus the scenario decision verdict | the same |
| `authoritative`, `stale_risk` | the scenario decision verdict | scenario decision verdict |
| `unity_completed_confirmed`, `unity_completed_filter_no_match`, `unity_failed_confirmed`, `unity_unproven`, `request_not_observed`, `wrapper_failed_unity_unproven` | the host's request final status | request final status, wrapper compact output |
| empty | a payload that never took a sample: a scenario step still pending, a step the run never reached, or a nested payload that could not be read | never read as a confirmation |

`playmode_throttled` is deliberately the same token in `result_trust_class` and
in `playmode_liveness_warning`, and `playmode_liveness_unproven` shares its stem
with `playmode_liveness_unproven_editor_unfocused`. Match on the field, never on
the bare string. Unifying the two namespaces is a breaking rename and is not
done in a patch release.

### `console_error_count_trust_class`

| Value | Meaning |
| --- | --- |
| `complete_since_request_start` | the counter session survived the whole request |
| `lower_bound_after_domain_reload` | the baseline belongs to a previous editor domain |
| `lower_bound_without_request_baseline` | no baseline establishes completeness |
| empty | the payload carries no console-pressure evidence at all |

### Play-mode liveness warnings and their remediation

| Warning | Remediation |
| --- | --- |
| `playmode_throttled` | `focus_the_unity_editor_or_set_interaction_mode_to_no_throttling` |
| `playmode_throttled_editor_unfocused` | the same |
| `playmode_liveness_unproven_editor_unfocused` | `wait_for_playmode_liveness_sample_and_retry` |
| empty | none |

### UI interaction outcomes and gaps

| Value | Meaning |
| --- | --- |
| `effective` | delivered and the before/after UI signature changed |
| `delivered_no_observable_effect` | delivered, no signature change; the direct tool reports it as a failure and a scenario step reports it as a pass only when `expectStateChange` waived the change |
| `not_delivered` | the event never reached a handler |
| `no_state_change` | a gap raised only when the step expected a change |
| `interaction_delivered` | the scenario step outcome for an effective click |
| `ui_target_occluded` | refused: a live event-system raycast at the target's centre resolved to a different click handler, so a real pointer would never reach the target |

### `pointer_raycast_evidence`

Where the `pointerCurrentRaycast` carried by a delivered click came from. A handler that
validates raycast identity (`eventData.pointerCurrentRaycast.gameObject == gameObject`) is
satisfied in every case below; the value says whether occlusion was actually ruled out.

| Value | Meaning |
| --- | --- |
| `event_system_raycast_resolves_to_handler` | a live `EventSystem.RaycastAll` at the target's centre hit a node resolving to the same handler, and that observed result was carried verbatim; occlusion is ruled out |
| `event_system_raycast_hit_other_handler` | the raycast resolved to a different handler; the click is refused as `ui_target_occluded` and never delivered |
| `synthesized_no_raycast_hit` | the raycast produced no hit, so the event carries a synthesized result naming the resolved handler; delivery is real, occlusion is unproven |
| `synthesized_no_event_system` | no `EventSystem.current` existed (typically Edit Mode), same synthesis and the same unproven occlusion |

A synthesized value always comes with the `ui_click_pointer_raycast_synthesized` warning; an
observed one never does.

### `pointer_targetable` and `pointer_target_status`

Whether a real pointer at a node's centre would land on its uGUI `Graphic`, by the filters
`GraphicRaycaster` and `Graphic.Raycast` apply. Render alpha is not one of them, so `visible`
(render visibility) and `pointer_targetable` are independent: an alpha-0 `Image` with
`raycastTarget` is `visible=false`, `pointer_targetable=true`. Depth and occlusion are left to
the live raycast described by `pointer_raycast_evidence`.

On a UI tree node the status describes the node's own `Graphic`, evaluated only for active
nodes whose bounds were requested; on a click payload it describes the click as a whole, where
any `Graphic` under the handler whose click bubbles to it may carry the pointer
(`pointer_target_path`). On a refused click the status and `pointer_target_blocked_by`
describe the target: its own `Graphic`, or without one the filter chain above it. The
scenario `ui_click` step block carries the status, the blocker, and the transparent-hit-area
fields.

| Value | Meaning |
| --- | --- |
| `targetable` | every filter accepts the pointer at the centre |
| `not_evaluated` | the node has no uGUI `Graphic`, is inactive, is a prefab asset, or had no bounds requested; on a click, it was refused before this check |
| `graphic_inactive` | the `Graphic` component is disabled |
| `raycast_target_disabled` | `raycastTarget=false` |
| `no_active_canvas` | the `Graphic` has no active, enabled `Canvas` above it, so no raycaster owns it |
| `no_raycaster` | the owning `Canvas` (the nearest one, for nested canvases) has no enabled `BaseRaycaster` |
| `canvas_renderer_culled` | `CanvasRenderer.cull` is set, typically by a `RectMask2D` |
| `outside_raycast_area` | the centre falls outside the rect after `raycastPadding` |
| `canvas_group_blocks_raycasts` | an enabled `CanvasGroup` in scope has `blocksRaycasts=false` |
| `alpha_hit_test_rejected` | an `Image` with `alphaHitTestMinimumThreshold > 0` sampled a pixel below the threshold |
| `raycast_filter_rejected` | another `ICanvasRaycastFilter` (a `Mask`, `RectMask2D`, or project filter) rejected the point |
| `no_pointer_targetable_graphic` | click only: the target has no `Graphic` and nothing under its handler accepts the pointer |

A render-invisible target keeps `ui_target_not_visible` unless it is interactable, has a click
handler, and a pointer target reaches that handler, so hidden panels refuse exactly as before.
A visible target the gate refuses is `ui_target_does_not_block_raycasts` when a `CanvasGroup`
blocks it and `ui_target_not_pointer_targetable` otherwise. An `Image` whose sprite texture is
not readable or is Crunch-compressed is accepted without sampling, as Unity accepts it after
logging an error. The event camera follows `GraphicRaycaster.eventCamera`: none for overlay
canvases and for screen-space-camera canvases without a camera, otherwise the canvas camera or
`Camera.main`.

### `transparent_hit_area_evidence`

Set when the `Graphic` carrying the click renders nothing (alpha 0 through its colour, its
`CanvasRenderer` alpha or colour as set by `CrossFadeAlpha`/`CrossFadeColor`, culling, or a
`CanvasGroup`) but Unity still raycasts it. The click is delivered either way.

| Value | Meaning |
| --- | --- |
| `visible_descendant_renders` | a rendered descendant (`transparent_hit_area_visible_path`) is drawn over the hit area, the usual icon-button pattern |
| `no_visible_descendant` | nothing under the hit area renders; the click carries the `ui_click_transparent_hit_area_without_visible_content` warning |
| empty | the hit area renders, or the click was refused first |

### `background_execution_mode`

| Value | Meaning |
| --- | --- |
| `project_owned` | the bridge does not touch `Application.runInBackground`; the project setting stands |
| `managed` | the project opted in, the bridge enabled it, and it restores the original value on disable or editor quit |

### `currency_basis`

| Value | Meaning |
| --- | --- |
| `editor_domain_load_vs_newest_assets_editor_input` | the verdict compares the loaded editor domain against the newest editor input under `Assets` |
| `settled_forced_asset_refresh_covers_newest_assets_editor_input` | a completed forced refresh already covered that input, and script compilation is not failing, so no reload was owed |
