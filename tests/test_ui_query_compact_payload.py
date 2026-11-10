"""ui_query / ui_exists / ui_get_text nodes are compact by default (RG-51)."""

import json
import sys
import unittest
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_bridge_payloads

NODE = {
    "node_id": "n_1234567890abcdef", "path": "Canvas/SafeArea/Tabs/TabQuests/Button", "parent_path": "Canvas/SafeArea/Tabs/TabQuests",
    "depth": 4, "sibling_index": 2, "child_count": 3, "name": "Button", "type": "Button", "scene_name": "Lobby",
    "components": ["RectTransform", "CanvasRenderer", "Image", "Button"], "active_self": True, "active_in_hierarchy": True,
    "visible": True, "visible_via_descendant": False, "visible_descendant_path": "", "interactable": True,
    "interactable_known": True, "effective_alpha": 1.0, "blocks_raycasts": True, "raycast_target": True,
    "raycast_target_known": True, "pointer_targetable": True, "pointer_target_status": "targetable",
    "canvas_path": "Canvas", "canvas_sort_order": 10, "render_order": 245, "has_bounds": True,
    "bounds": {"x": 812.5, "y": 2890.0, "width": 240.0, "height": 180.0}, "bounds_space": "screen_pixels",
    "has_text": True, "text": "Quests", "text_source": "TextMeshProUGUI", "font": "Roboto-Bold SDF",
    "font_resolved_status": "resolved", "material": "Roboto-Bold SDF Material", "material_resolved_status": "resolved",
    "sprite": "btn_tab_active", "clip_state": "not_clipped", "clipped_by": "", "component_details_complete": True,
    "component_detail_backend": "ugui", "children_truncated": False,
}


def response(payload_type: str, matches: list) -> dict:
    payload = {"operation": payload_type, "success": True, "match_count": len(matches), "matches": matches,
               "component_detail_backends": ["ugui", "tmp"], "playmode_loop_liveness": "advancing"}
    return {"status": "ok", "payload_type": payload_type, "payload_json": json.dumps(payload)}


def convert(resp: dict, include_full_payload: bool) -> dict:
    return server_bridge_payloads.bridge_response_to_tool_result(
        resp,
        normalize_scenario_payload=lambda payload, statuses: payload,
        scenario_terminal_statuses=set(),
        include_full_payload=include_full_payload,
    )["structuredContent"]


class UiQueryCompactPayloadTests(unittest.TestCase):
    def test_default_projection_keeps_decision_fields_and_shrinks_nodes(self) -> None:
        dimmed = dict(NODE, path="Canvas/Popup/Close", effective_alpha=0.4, interactable_known=True, interactable=False)
        full = convert(response("unity.ui.query", [NODE] * 9 + [dimmed]), True)
        compact = convert(response("unity.ui.query", [NODE] * 9 + [dimmed]), False)

        self.assertEqual("compact_ui_query", compact["payload_mode"])
        node = compact["matches"][0]
        self.assertEqual(
            {"path", "name", "type", "scene_name", "components", "active_in_hierarchy", "visible", "interactable",
             "pointer_target_status", "bounds", "text"},
            set(node),
        )
        self.assertEqual({"effective_alpha": 0.4, "interactable": False}, {k: compact["matches"][-1][k] for k in ("effective_alpha", "interactable")})
        self.assertEqual("advancing", compact["playmode_loop_liveness"])
        self.assertNotIn("component_detail_backends", compact)
        self.assertLess(len(json.dumps(compact)), len(json.dumps(full)) * 0.45)
        self.assertEqual(NODE, full["matches"][0])

    def test_exists_and_get_text_share_the_projection(self) -> None:
        for payload_type in ("unity.ui.exists", "unity.ui.get_text"):
            compact = convert(response(payload_type, [NODE]), False)
            self.assertNotIn("node_id", compact["matches"][0])


class PrefabRefusalCompactPayloadTests(unittest.TestCase):
    def refusal(self, status: str = "blocked", changes: list | None = None) -> dict:
        payload = {
            "operation": "unity.prefab.mutate", "success": False, "status": status, "prefab_path": "Assets/P.prefab",
            "requested_operation_count": 96, "changes": changes or [],
            "errors": [{"code": "prefab_mutation_operations_limit", "message": "at most 64", "detail": "96"}],
            "warnings": [], "recommended_next_action": "fix_the_transaction_shape_then_preview_again",
            "post_validation": {"defects": [], "status": "failed"}, "artifact_manifest": {"groups": {"x": ["y" * 900]}},
            "structured_timing": {"phases": ["z" * 300]},
        }
        return {"status": "ok", "payload_type": "unity.prefab.mutate", "payload_json": json.dumps(payload)}

    def test_a_refusal_before_any_change_drops_the_service_blocks(self) -> None:
        compact = convert(self.refusal(), False)

        self.assertEqual("compact_refusal", compact["payload_mode"])
        self.assertEqual("prefab_mutation_operations_limit", compact["errors"][0]["code"])
        self.assertEqual(96, compact["requested_operation_count"])
        for heavy in ("post_validation", "artifact_manifest", "structured_timing", "changes"):
            self.assertNotIn(heavy, compact)
        self.assertIn("artifact_manifest", convert(self.refusal(), True))

    def test_a_rolled_back_or_previewed_transaction_keeps_its_changes(self) -> None:
        rolled_back = convert(self.refusal(status="rolled_back", changes=[{"index": 0, "status": "failed"}]), False)
        self.assertIn("changes", rolled_back)
        self.assertNotEqual("compact_refusal", rolled_back.get("payload_mode"))


if __name__ == "__main__":
    unittest.main()
