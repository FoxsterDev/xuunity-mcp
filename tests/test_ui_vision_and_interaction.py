"""Vision review lane (xuunity.ui-vision-review.v1) and interaction lane (xuunity.ui-interaction.v1).

Two lanes a cell-similarity score cannot cover:

- vision: a multimodal judge answers "is this recognisably the same screen", under a rubric
  whose arithmetic is checked, bound to one exact image pair, with the judge's role recorded;
- interaction: a guarded click delivered inside a Play-mode scenario, read back from the
  scenario receipt. Edit-mode delivery is reported as unproven, never as a pass.

The seam between them matters most when they disagree with the numeric comparison, so the
disagreement analysis is pinned here too.
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = TESTS_DIR.parent / "templates"
for entry in (TEMPLATES_DIR, TESTS_DIR):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import server_specs
from server_core import ToolInvocationError
from server_ui_reference_compare import compare_ui_reference
from server_ui_vision_packet import build_vision_packet, submit_vision_review
from test_ui_reference_acceptance import UiReferenceTestCase, write_image
from server_ui_interaction import (
    UI_INTERACTION_SCHEMA_VERSION,
    evaluate_interaction_lane,
    normalize_ui_interaction,
    read_scenario_ui_interactions,
)
from server_ui_reference_manifest import DEFAULT_LANE_REQUIREMENTS, TOLERANCE_PROFILES
from server_ui_reference_png import RgbaImage, decode_png, encode_png
from server_ui_reference_verdict import finalize_comparison
from server_ui_vision_review import (
    CRITERIA,
    SCALE_MAX,
    UI_VISION_SCHEMA_VERSION,
    analyze_lane_disagreement,
    evaluate_vision_lane,
    normalize_vision_review,
    packet_hash,
    resolve_vision_policy,
)
from server_ui_vision_sheet import render_review_sheet

REPO_ROOT = Path(__file__).resolve().parents[1]
EDITOR_ROOT = REPO_ROOT / "packages" / "com.xuunity.light-mcp" / "Editor"

BALANCED = resolve_vision_policy({"tolerance_profile": "balanced"})


def review(**overrides):
    body = {
        "schema_version": UI_VISION_SCHEMA_VERSION,
        "packet_hash": "abc",
        "judge": {"id": "judge-1", "role": "independent_agent", "model": "test"},
        "overall": 3,
        "criteria": {name: {"score": 3, "observation": f"{name} matches"} for name in CRITERIA},
    }
    body.update(overrides)
    return body


def solid(width: int, height: int, color) -> RgbaImage:
    return RgbaImage(width=width, height=height, pixels=bytes(color) * (width * height))


class VisionRubricTests(unittest.TestCase):
    def test_a_complete_review_at_the_bar_passes(self) -> None:
        record = normalize_vision_review(review(), policy=BALANCED, expected_packet_hash="abc")
        self.assertTrue(record["valid"], record["errors"])
        self.assertEqual("passed", record["verdict"])

    def test_a_criterion_without_an_observation_is_invalid(self) -> None:
        criteria = {name: {"score": 3, "observation": "ok"} for name in CRITERIA}
        criteria["layout"] = {"score": 3, "observation": ""}
        record = normalize_vision_review(
            review(criteria=criteria), policy=BALANCED, expected_packet_hash="abc"
        )
        self.assertIn("missing_observation_layout", record["errors"])
        self.assertEqual("blocked", record["verdict"])

    def test_a_missing_required_criterion_is_invalid(self) -> None:
        criteria = {name: {"score": 3, "observation": "ok"} for name in CRITERIA if name != "content"}
        record = normalize_vision_review(
            review(criteria=criteria), policy=BALANCED, expected_packet_hash="abc"
        )
        self.assertIn("missing_criterion_content", record["errors"])

    def test_overall_cannot_outrun_the_worst_required_criterion(self) -> None:
        criteria = {name: {"score": 4, "observation": "ok"} for name in CRITERIA}
        criteria["layout"] = {"score": 1, "observation": "CTA is on the wrong side"}
        record = normalize_vision_review(
            review(overall=4, criteria=criteria), policy=BALANCED, expected_packet_hash="abc"
        )
        self.assertEqual(4, record["overall_reported"])
        self.assertEqual(2, record["overall_effective"])
        self.assertIn("overall_clamped_to_worst_criterion", record["warnings"])
        self.assertEqual("failed", record["verdict"])

    def test_a_criterion_below_the_profile_floor_fails_the_review(self) -> None:
        criteria = {name: {"score": 3, "observation": "ok"} for name in CRITERIA}
        criteria["imagery"] = {"score": 1, "observation": "different icon set"}
        record = normalize_vision_review(
            review(criteria=criteria), policy=BALANCED, expected_packet_hash="abc"
        )
        self.assertEqual("failed", record["verdict"])
        self.assertEqual(["imagery"], record["failed_criteria"])

    def test_the_bar_moves_with_the_tolerance_profile(self) -> None:
        criteria = {name: {"score": 2, "observation": "visibly different but same intent"} for name in CRITERIA}
        body = review(overall=2, criteria=criteria)
        lenient = normalize_vision_review(
            body, policy=resolve_vision_policy({"tolerance_profile": "lenient"}), expected_packet_hash="abc"
        )
        strict = normalize_vision_review(
            body, policy=resolve_vision_policy({"tolerance_profile": "strict"}), expected_packet_hash="abc"
        )
        self.assertEqual("passed", lenient["verdict"])
        self.assertEqual("failed", strict["verdict"])

    def test_pixel_equality_is_never_required_by_any_profile(self) -> None:
        for name in ("strict", "balanced", "lenient"):
            policy = resolve_vision_policy({"tolerance_profile": name})
            self.assertLess(policy["min_overall"], SCALE_MAX, name)
            self.assertLess(policy["min_criterion"], SCALE_MAX, name)

    def test_a_manifest_can_override_the_bar_and_waive_a_criterion(self) -> None:
        policy = resolve_vision_policy(
            {
                "tolerance_profile": "balanced",
                "vision_policy": {"min_overall": 2, "required_criteria": ["layout", "sizing"]},
            }
        )
        self.assertEqual(2, policy["min_overall"])
        self.assertEqual(["layout", "sizing"], policy["required_criteria"])
        record = normalize_vision_review(
            review(overall=2, criteria={"layout": {"score": 2, "observation": "close"},
                                        "sizing": {"score": 2, "observation": "close"}}),
            policy=policy,
            expected_packet_hash="abc",
        )
        self.assertEqual("passed", record["verdict"])


class VisionPolicyFloorTests(unittest.TestCase):
    """The bar is caller-authored data, so it needs a floor and validation of its own."""

    def test_a_zero_bar_is_raised_to_the_floor(self) -> None:
        policy = resolve_vision_policy(
            {"tolerance_profile": "balanced", "vision_policy": {"min_criterion": 0, "min_overall": 0}}
        )
        self.assertEqual(1, policy["min_criterion"])
        self.assertEqual(1, policy["min_overall"])

    def test_an_all_absent_review_cannot_pass_any_profile(self) -> None:
        for profile in ("strict", "balanced", "lenient"):
            policy = resolve_vision_policy(
                {"tolerance_profile": profile, "vision_policy": {"min_criterion": 0, "min_overall": 0}}
            )
            record = normalize_vision_review(
                review(
                    overall=0,
                    criteria={name: {"score": 0, "observation": "absent"} for name in CRITERIA},
                ),
                policy=policy,
                expected_packet_hash="abc",
            )
            self.assertEqual("failed", record["verdict"], profile)

    def test_every_criterion_on_the_bare_floor_does_not_pass_balanced(self) -> None:
        record = normalize_vision_review(
            review(
                overall=3,
                criteria={name: {"score": 2, "observation": "visibly different"} for name in CRITERIA},
            ),
            policy=BALANCED,
            expected_packet_hash="abc",
        )
        self.assertEqual(2, record["overall_effective"])
        self.assertEqual("failed", record["verdict"])
        self.assertIn("overall_clamped_to_criteria_corroboration", record["warnings"])

    def test_one_weak_criterion_among_strong_ones_still_passes(self) -> None:
        criteria = {name: {"score": 4, "observation": f"{name} matches"} for name in CRITERIA}
        criteria["typography"] = {"score": 2, "observation": "font weight differs"}
        record = normalize_vision_review(
            review(overall=4, criteria=criteria), policy=BALANCED, expected_packet_hash="abc"
        )
        self.assertEqual(3, record["overall_effective"])
        self.assertEqual("passed", record["verdict"])

    def test_a_case_variant_criterion_key_is_a_duplicate_not_an_overwrite(self) -> None:
        criteria = {name: {"score": 4, "observation": f"{name} matches"} for name in CRITERIA}
        criteria["layout"] = {"score": 0, "observation": "CTA absent"}
        criteria["LAYOUT"] = {"score": 4, "observation": "looks fine to me"}
        record = normalize_vision_review(
            review(overall=4, criteria=criteria), policy=BALANCED, expected_packet_hash="abc"
        )
        self.assertIn("duplicate_criterion_layout", record["errors"])
        self.assertFalse(record["valid"])

    def test_an_unknown_criterion_is_an_error_not_a_silent_drop(self) -> None:
        criteria = {name: {"score": 4, "observation": f"{name} matches"} for name in CRITERIA}
        criteria["colour"] = {"score": 0, "observation": "wrong palette"}
        record = normalize_vision_review(
            review(overall=4, criteria=criteria), policy=BALANCED, expected_packet_hash="abc"
        )
        self.assertIn("unknown_criterion_colour", record["errors"])
        self.assertFalse(record["valid"])

    def test_the_independence_bar_is_inside_the_packet_hash(self) -> None:
        strict_panel = resolve_vision_policy(
            {"vision_policy": {"judges_required": 3, "allow_self_review": False}}
        )
        lax_panel = resolve_vision_policy(
            {"vision_policy": {"judges_required": 1, "allow_self_review": True}}
        )
        material = {"reference_id": "ref", "expected_sha256": "a" * 64, "actual_sha256": "b" * 64}
        self.assertNotEqual(
            packet_hash(policy=strict_panel, **material),
            packet_hash(policy=lax_panel, **material),
        )


class VisionProvenanceTests(unittest.TestCase):
    def test_a_review_bound_to_another_image_pair_is_stale(self) -> None:
        record = normalize_vision_review(review(), policy=BALANCED, expected_packet_hash="different")
        self.assertIn("vision_packet_stale", record["errors"])
        self.assertEqual("blocked", record["verdict"])

    def test_the_packet_hash_changes_when_either_image_changes(self) -> None:
        base = dict(reference_id="r", expected_sha256="a", actual_sha256="b", policy=BALANCED)
        self.assertNotEqual(packet_hash(**base), packet_hash(**{**base, "actual_sha256": "c"}))
        self.assertNotEqual(packet_hash(**base), packet_hash(**{**base, "expected_sha256": "c"}))

    def test_the_packet_hash_changes_when_the_bar_changes(self) -> None:
        base = dict(reference_id="r", expected_sha256="a", actual_sha256="b")
        strict = resolve_vision_policy({"tolerance_profile": "strict"})
        self.assertNotEqual(
            packet_hash(**base, policy=BALANCED), packet_hash(**base, policy=strict)
        )

    def test_self_review_passes_but_is_flagged(self) -> None:
        body = review(judge={"id": "me", "role": "authoring_agent", "model": "test"})
        record = normalize_vision_review(body, policy=BALANCED, expected_packet_hash="abc")
        self.assertEqual("passed", record["verdict"])
        self.assertIn("vision_review_is_self_reviewed", record["warnings"])
        lane = evaluate_vision_lane(reviews=[record], policy=BALANCED, requirement="required")
        self.assertTrue(lane["self_reviewed_only"])

    def test_self_review_can_be_refused_outright(self) -> None:
        policy = resolve_vision_policy(
            {"tolerance_profile": "balanced", "vision_policy": {"allow_self_review": False}}
        )
        body = review(judge={"id": "me", "role": "authoring_agent", "model": "test"})
        record = normalize_vision_review(body, policy=policy, expected_packet_hash="abc")
        self.assertIn("vision_self_review_not_permitted", record["errors"])

    def test_an_unnamed_judge_is_refused(self) -> None:
        record = normalize_vision_review(
            review(judge={"role": "human"}), policy=BALANCED, expected_packet_hash="abc"
        )
        self.assertIn("missing_judge_id", record["errors"])


class VisionLaneTests(unittest.TestCase):
    def test_no_review_leaves_the_lane_unevaluated(self) -> None:
        lane = evaluate_vision_lane(reviews=[], policy=BALANCED, requirement="optional")
        self.assertEqual("not_evaluated", lane["status"])

    def test_a_split_panel_reports_the_disagreement(self) -> None:
        passing = normalize_vision_review(review(), policy=BALANCED, expected_packet_hash="abc")
        failing_criteria = {name: {"score": 3, "observation": "ok"} for name in CRITERIA}
        failing_criteria["color"] = {"score": 0, "observation": "panel is missing"}
        failing = normalize_vision_review(
            review(judge={"id": "judge-2", "role": "human", "model": ""}, criteria=failing_criteria),
            policy=BALANCED,
            expected_packet_hash="abc",
        )
        lane = evaluate_vision_lane(reviews=[passing, failing], policy=BALANCED, requirement="required")
        self.assertEqual("failed", lane["status"])
        self.assertFalse(lane["unanimous"])
        self.assertEqual("color", lane["worst_criteria"][0]["criterion"])

    def test_too_few_judges_blocks_rather_than_passes(self) -> None:
        policy = resolve_vision_policy(
            {"tolerance_profile": "balanced", "vision_policy": {"judges_required": 2}}
        )
        record = normalize_vision_review(review(), policy=policy, expected_packet_hash="abc")
        lane = evaluate_vision_lane(reviews=[record], policy=policy, requirement="required")
        self.assertEqual("blocked", lane["status"])
        self.assertEqual("not_enough_judges", lane["blocked_reason"])


class DisagreementTests(unittest.TestCase):
    tolerances = dict(TOLERANCE_PROFILES["strict"])

    def test_agreement_is_not_reported_as_disagreement(self) -> None:
        lane = {"status": "passed"}
        result = analyze_lane_disagreement(
            visual_verdict="passed", vision_lane=lane, global_metrics={}, tolerances=self.tolerances
        )
        self.assertFalse(result["disagree"])

    def test_grid_pass_with_review_failure_trusts_the_review(self) -> None:
        lane = {"status": "failed", "worst_criteria": [{"criterion": "imagery", "score": 1}]}
        result = analyze_lane_disagreement(
            visual_verdict="passed",
            vision_lane=lane,
            global_metrics={"similarity_score": 0.99},
            tolerances=self.tolerances,
        )
        self.assertTrue(result["disagree"])
        self.assertEqual("vision_contradicts_similarity", result["code"])
        self.assertEqual("vision", result["trust"])
        self.assertIn("imagery", result["message"])

    def test_grid_failure_with_review_pass_suggests_a_looser_profile(self) -> None:
        result = analyze_lane_disagreement(
            visual_verdict="failed",
            vision_lane={"status": "passed"},
            global_metrics={"similarity_score": 0.95},
            tolerances=self.tolerances,
        )
        self.assertEqual("similarity_may_be_over_strict", result["code"])
        self.assertEqual("balanced", result["suggestion"]["tolerance_profile"])
        self.assertTrue(result["suggestion"]["would_pass_global"])

    def test_a_difference_beyond_every_profile_suggests_nothing(self) -> None:
        result = analyze_lane_disagreement(
            visual_verdict="failed",
            vision_lane={"status": "passed"},
            global_metrics={"similarity_score": 0.20},
            tolerances=self.tolerances,
        )
        self.assertFalse(result["suggestion"]["would_pass_global"])
        self.assertEqual("", result["suggestion"]["tolerance_profile"])

    def test_an_unevaluated_vision_lane_never_disagrees(self) -> None:
        result = analyze_lane_disagreement(
            visual_verdict="failed",
            vision_lane={"status": "not_evaluated"},
            global_metrics={"similarity_score": 0.5},
            tolerances=self.tolerances,
        )
        self.assertFalse(result["disagree"])


class ReviewSheetTests(unittest.TestCase):
    def test_the_sheet_places_the_reference_left_of_the_candidate(self) -> None:
        sheet, layout = render_review_sheet(
            expected=solid(40, 80, (255, 0, 0, 255)),
            actual=solid(40, 80, (0, 0, 255, 255)),
            max_panel_height=80,
        )
        self.assertLess(layout["reference_panel"]["x"], layout["candidate_panel"]["x"])
        self.assertEqual(80, layout["panel_height"])
        self.assertGreater(sheet.width, 80)

    def test_the_sheet_is_a_decodable_png_carrying_both_images(self) -> None:
        sheet, layout = render_review_sheet(
            expected=solid(20, 40, (255, 0, 0, 255)),
            actual=solid(20, 40, (0, 0, 255, 255)),
            max_panel_height=40,
        )
        decoded = decode_png(encode_png(sheet), source="sheet")
        self.assertEqual((sheet.width, sheet.height), (decoded.width, decoded.height))

        def pixel(panel):
            x = panel["x"] + panel["width"] // 2
            y = panel["y"] + panel["height"] // 2
            offset = (y * decoded.width + x) * 4
            return tuple(decoded.pixels[offset : offset + 3])

        self.assertEqual((255, 0, 0), pixel(layout["reference_panel"]))
        self.assertEqual((0, 0, 255), pixel(layout["candidate_panel"]))

    def test_panels_share_a_height_even_when_the_capture_resolution_differs(self) -> None:
        _, layout = render_review_sheet(
            expected=solid(100, 200, (10, 10, 10, 255)),
            actual=solid(50, 100, (10, 10, 10, 255)),
            max_panel_height=200,
        )
        self.assertEqual(
            layout["reference_panel"]["height"], layout["candidate_panel"]["height"]
        )
        self.assertEqual(layout["reference_panel"]["width"], layout["candidate_panel"]["width"])

    def test_failed_regions_are_marked_on_both_panels(self) -> None:
        _, layout = render_review_sheet(
            expected=solid(40, 80, (10, 10, 10, 255)),
            actual=solid(40, 80, (10, 10, 10, 255)),
            marked_regions=[{"region_id": "cta", "rect": {"x": 4, "y": 8, "width": 20, "height": 12}}],
            reference_viewport={"width": 40, "height": 80},
            max_panel_height=80,
        )
        self.assertEqual(1, len(layout["markers"]))
        marker = layout["markers"][0]
        self.assertEqual("cta", marker["region_id"])
        self.assertIn("drawn_on_reference_panel", marker)
        self.assertIn("drawn_on_candidate_panel", marker)


class InteractionContractTests(unittest.TestCase):
    def block(self, **overrides):
        body = {
            "schema_version": UI_INTERACTION_SCHEMA_VERSION,
            "interaction_id": "close_button",
            "action": "click",
            "delivered": True,
            "state_changed": True,
            "playmode_state": "playing",
            "target_path": "Canvas/Popup/CloseButton",
            "handler_path": "Canvas/Popup/CloseButton",
        }
        body.update(overrides)
        return body

    def test_a_playmode_delivery_is_runtime_proven(self) -> None:
        record = normalize_ui_interaction(
            self.block(), evidence_source="scenario_result", receipt={"step_status": "passed"}
        )
        self.assertTrue(record["runtime_proven"])
        self.assertEqual([], record["gaps"])

    def test_an_edit_mode_delivery_is_not_runtime_proven(self) -> None:
        record = normalize_ui_interaction(
            self.block(playmode_state="edit"),
            evidence_source="scenario_result",
            receipt={"step_status": "passed"},
        )
        self.assertFalse(record["runtime_proven"])
        self.assertIn("edit_mode_delivery", record["gaps"])

    def test_caller_asserted_evidence_is_never_receipt_backed(self) -> None:
        record = normalize_ui_interaction(self.block(), evidence_source="caller_asserted")
        self.assertIn("evidence_not_receipt_backed", record["gaps"])

    def test_a_refusal_is_reported_as_a_broken_path(self) -> None:
        record = normalize_ui_interaction(
            self.block(delivered=False, refusal_code="ui_target_not_interactable"),
            evidence_source="scenario_result",
            receipt={"step_status": "failed"},
        )
        self.assertIn("refused", record["gaps"])
        self.assertIn("step_failed", record["gaps"])
        self.assertFalse(record["runtime_proven"])

    def test_delivery_without_a_state_change_is_reported(self) -> None:
        record = normalize_ui_interaction(
            self.block(state_changed=False), evidence_source="scenario_result", receipt={"step_status": "passed"}
        )
        self.assertIn("no_state_change", record["gaps"])


class InteractionLaneTests(unittest.TestCase):
    proven = {
        "interaction_id": "close_button",
        "delivered": True,
        "state_changed": True,
        "runtime_proven": True,
        "target_path": "Canvas/Popup/CloseButton",
        "refusal_code": "",
        "gaps": [],
    }
    required = [{"id": "close_button", "expect": {"delivered": True, "state_changed": True}}]

    def test_a_proven_playmode_interaction_passes_the_lane(self) -> None:
        lane = evaluate_interaction_lane(
            interactions=[dict(self.proven)], required_interactions=self.required, requirement="required"
        )
        self.assertEqual("passed", lane["status"])

    def test_edit_mode_delivery_blocks_instead_of_passing(self) -> None:
        record = {**self.proven, "runtime_proven": False}
        lane = evaluate_interaction_lane(
            interactions=[record], required_interactions=self.required, requirement="required"
        )
        self.assertEqual("blocked", lane["status"])
        self.assertEqual(["close_button"], lane["edit_mode_only"])

    def test_a_required_interaction_never_exercised_fails(self) -> None:
        lane = evaluate_interaction_lane(
            interactions=[], required_interactions=self.required, requirement="required"
        )
        self.assertEqual("failed", lane["status"])
        self.assertEqual("interaction_not_reported", lane["failures"][0]["code"])

    def test_a_missing_state_change_fails_when_expected(self) -> None:
        record = {**self.proven, "state_changed": False}
        lane = evaluate_interaction_lane(
            interactions=[record], required_interactions=self.required, requirement="required"
        )
        self.assertEqual("failed", lane["status"])
        self.assertEqual("no_state_change", lane["failures"][0]["code"])

    def test_a_state_change_can_be_waived_per_interaction(self) -> None:
        record = {**self.proven, "state_changed": False}
        lane = evaluate_interaction_lane(
            interactions=[record],
            required_interactions=[{"id": "close_button", "expect": {"state_changed": False}}],
            requirement="required",
        )
        self.assertEqual("passed", lane["status"])

    def test_an_interaction_matches_by_selector_when_the_id_differs(self) -> None:
        record = {**self.proven, "interaction_id": "other"}
        lane = evaluate_interaction_lane(
            interactions=[record],
            required_interactions=[{"id": "close_button", "selector": {"path": "Canvas/Popup/CloseButton"}}],
            requirement="required",
        )
        self.assertEqual("passed", lane["status"])

    def test_interactions_are_read_out_of_a_scenario_receipt(self) -> None:
        payload = {
            "run_id": "run-1",
            "status": "passed",
            "steps": [
                {
                    "stepId": "close_popup",
                    "kind": "ui_click",
                    "status": "passed",
                    "payload_json": json.dumps(
                        {
                            "ui_interaction": {
                                "schema_version": UI_INTERACTION_SCHEMA_VERSION,
                                "interaction_id": "close_button",
                                "delivered": True,
                                "state_changed": True,
                                "playmode_state": "playing",
                            }
                        }
                    ),
                }
            ],
        }
        with tempfile.TemporaryDirectory() as workspace:
            path = Path(workspace) / "result.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            records, receipt = read_scenario_ui_interactions(path)

        self.assertEqual(1, len(records))
        self.assertTrue(records[0]["runtime_proven"])
        self.assertEqual("scenario_result", records[0]["evidence_source"])
        self.assertEqual("close_popup", records[0]["receipt"]["step_id"])
        self.assertEqual(64, len(receipt["sha256"]))


class LaneVerdictIntegrationTests(unittest.TestCase):
    def finalize(self, **overrides):
        acceptance = overrides.pop("acceptance", None) or dict(DEFAULT_LANE_REQUIREMENTS)
        global_metrics = overrides.pop("global_metrics", None) or {"similarity_score": 0.99}
        result = {
            "visual_verdict": "passed",
            "failure_reasons": [],
            "warnings": [],
            "owner": "agent",
            "capture_stability": {"status": "proven"},
            "fixture": {"declared_fixture": "f", "determinism_gaps": []},
            "global": global_metrics,
            "tolerances": dict(TOLERANCE_PROFILES["balanced"]),
            "comparison_id": "c1",
            "semantic_lane": {"status": "passed", "evidence": "", "checked": 1, "failures": []},
        }
        result.update(overrides)
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            return finalize_comparison(
                result,
                project_root=root,
                workspace=root,
                reference_dir=root,
                manifest={"acceptance": acceptance},
                blocked_reason="",
                blocked_message="",
                register_in_artifact_registry=False,
                emit_artifacts=False,
            )

    def test_a_failed_vision_review_fails_a_visually_passing_comparison(self) -> None:
        result = self.finalize(
            vision_lane={
                "status": "failed",
                "evidence": "",
                "worst_criteria": [{"criterion": "imagery", "score": 1, "name": "wrong",
                                    "observation": "different icon"}],
            },
            interaction_lane={"status": "passed", "evidence": "", "failures": []},
        )
        self.assertEqual("failed", result["reference_acceptance"])
        self.assertIn("vision", result["failed_lanes"])
        self.assertTrue(any("imagery" in reason for reason in result["failure_reasons"]))

    def test_an_optional_lane_that_ran_and_failed_still_fails_the_comparison(self) -> None:
        result = self.finalize(
            acceptance={**DEFAULT_LANE_REQUIREMENTS, "vision": "optional"},
            vision_lane={"status": "failed", "evidence": "", "worst_criteria": []},
            interaction_lane={"status": "passed", "evidence": "", "failures": []},
        )
        self.assertEqual("optional", result["acceptance_lanes"]["vision"]["requirement"])
        self.assertEqual("failed", result["reference_acceptance"])

    def test_a_not_required_lane_that_failed_is_ignored(self) -> None:
        result = self.finalize(
            acceptance={**DEFAULT_LANE_REQUIREMENTS, "vision": "not_required"},
            vision_lane={"status": "failed", "evidence": "", "worst_criteria": []},
            interaction_lane={"status": "passed", "evidence": "", "failures": []},
        )
        self.assertNotIn("vision", result["failed_lanes"])
        self.assertEqual("passed", result["reference_acceptance"])

    def test_an_edit_mode_only_interaction_blocks_the_comparison(self) -> None:
        result = self.finalize(
            interaction_lane={
                "status": "blocked",
                "evidence": "",
                "failures": [],
                "blocked_reason": "edit_mode_delivery_does_not_prove_a_runtime_user_path",
            }
        )
        self.assertEqual("blocked", result["reference_acceptance"])
        self.assertIn("interaction", result["blocked_lanes"])
        self.assertIn("interaction_lane_blocked", result["decision_readiness_gaps"])

    def test_an_optional_lane_that_ran_and_blocked_still_gates_the_verdict(self) -> None:
        acceptance = dict(DEFAULT_LANE_REQUIREMENTS)
        acceptance["interaction"] = "optional"
        result = self.finalize(
            acceptance=acceptance,
            interaction_lane={
                "status": "blocked",
                "evidence": "",
                "failures": [],
                "blocked_reason": "edit_mode_delivery_does_not_prove_a_runtime_user_path",
            },
        )
        self.assertEqual("blocked", result["reference_acceptance"])
        self.assertIn("interaction", result["blocked_lanes"])
        self.assertFalse(result["decision_ready"])

    def test_an_optional_vision_lane_blocked_by_a_stale_review_still_gates(self) -> None:
        result = self.finalize(
            vision_lane={
                "status": "blocked",
                "evidence": "",
                "worst_criteria": [],
                "blocked_reason": "invalid_review_submitted",
            }
        )
        self.assertEqual("optional", result["acceptance_lanes"]["vision"]["requirement"])
        self.assertEqual("blocked", result["reference_acceptance"])
        self.assertIn("vision", result["blocked_lanes"])
        self.assertFalse(result["decision_ready"])

    def test_a_not_required_lane_that_blocked_still_opts_out(self) -> None:
        acceptance = dict(DEFAULT_LANE_REQUIREMENTS)
        acceptance["interaction"] = "not_required"
        result = self.finalize(
            acceptance=acceptance,
            interaction_lane={
                "status": "blocked",
                "evidence": "",
                "failures": [],
                "blocked_reason": "edit_mode_delivery_does_not_prove_a_runtime_user_path",
            },
        )
        self.assertEqual([], result["blocked_lanes"])
        self.assertEqual("passed", result["reference_acceptance"])

    def test_a_self_reviewed_pass_is_not_decision_ready(self) -> None:
        result = self.finalize(
            interaction_lane={"status": "passed", "evidence": "", "failures": []},
            vision_lane={
                "status": "passed",
                "evidence": "",
                "worst_criteria": [],
                "self_reviewed_only": True,
            },
        )
        self.assertEqual("passed", result["reference_acceptance"])
        self.assertIn("vision_self_reviewed_only", result["decision_readiness_gaps"])
        self.assertFalse(result["decision_ready"])

    def test_the_over_strict_suggestion_reaches_next_actions(self) -> None:
        result = self.finalize(
            visual_verdict="failed",
            tolerances=dict(TOLERANCE_PROFILES["strict"]),
            global_metrics={"similarity_score": 0.95},
            vision_lane={"status": "passed", "evidence": "", "worst_criteria": []},
            interaction_lane={"status": "passed", "evidence": "", "failures": []},
        )
        codes = [warning["code"] for warning in result["warnings"]]
        self.assertIn("similarity_may_be_over_strict", codes)
        self.assertTrue(any("balanced" in action for action in result["next_actions"]))

    def test_vision_stays_out_of_the_way_when_no_review_exists(self) -> None:
        result = self.finalize(interaction_lane={"status": "passed", "evidence": "", "failures": []})
        self.assertEqual("not_evaluated", result["acceptance_lanes"]["vision"]["status"])
        self.assertEqual("passed", result["reference_acceptance"])
        self.assertNotIn("vision", result["pending_lanes"])


class VisionRoundTripTests(UiReferenceTestCase):
    """packet -> judge -> submit -> compare, over real files on disk."""

    def setUp(self) -> None:
        super().setUp()
        self.register(
            solid(120, 240, (40, 80, 160, 255)),
            acceptance={"visual": "required", "semantic": "not_required",
                        "interaction": "not_required", "vision": "required"},
        )
        self.capture = write_image(self.captures / "candidate.png", solid(120, 240, (40, 80, 160, 255)))

    def build_packet(self, **overrides) -> dict:
        payload = {
            "project_root": self.project_root,
            "reference_id": "popup-available-v1",
            "actual_image": str(self.capture),
            "comparison_id": "fixed-comparison",
            "workspace_root": str(self.workspace),
        }
        payload.update(overrides)
        return build_vision_packet(**payload)

    def judgement(self, packet: dict, **overrides) -> dict:
        body = review(packet_hash=packet["packet_hash"])
        body.update(overrides)
        return body

    def test_the_packet_writes_a_sheet_and_a_hash_bound_manifest(self) -> None:
        packet = self.build_packet()
        sheet = Path(packet["sheet"]["path"])
        self.assertTrue(sheet.is_file())
        self.assertEqual(64, len(packet["packet_hash"]))
        decoded = decode_png(sheet.read_bytes(), source="sheet")
        self.assertEqual(decoded.width, packet["sheet"]["sheet"]["width"])
        self.assertEqual("failed_regions_marked_scores_withheld", packet["attention"]["anchoring"])
        self.assertNotIn("numeric_evidence", packet)

    def test_the_rubric_travels_with_the_packet(self) -> None:
        packet = self.build_packet()
        criteria = [entry["id"] for entry in packet["rubric"]["criteria"]]
        self.assertEqual(list(CRITERIA), criteria)
        self.assertIn("Pixel equality", packet["rubric"]["question"])

    def test_an_invalid_review_is_refused_and_never_stored(self) -> None:
        packet = self.build_packet()
        with self.assertRaises(ToolInvocationError) as caught:
            submit_vision_review(
                project_root=self.project_root,
                packet_path=packet["packet_path"],
                review=self.judgement(packet, packet_hash="stale-hash"),
                workspace_root=str(self.workspace),
            )
        self.assertEqual("ui_vision_review_invalid", caught.exception.code)
        stored = list(Path(packet["packet_path"]).parent.glob("vision_review.*.json"))
        self.assertEqual([], stored)

        # The comparison is still decidable; a refused submission left no residue behind.
        result = compare_ui_reference(
            project_root=self.project_root,
            reference_id="popup-available-v1",
            actual_image=str(self.capture),
            stability_image=str(self.capture),
            comparison_id="fixed-comparison",
            workspace_root=str(self.workspace),
            register_in_artifact_registry=False,
        )
        self.assertEqual("not_evaluated", result["acceptance_lanes"]["vision"]["status"])

    def test_a_second_submission_by_the_same_judge_is_refused(self) -> None:
        packet = self.build_packet()
        submit_vision_review(
            project_root=self.project_root,
            packet_path=packet["packet_path"],
            review=self.judgement(
                packet,
                overall=1,
                criteria={name: {"score": 1, "observation": "wrong"} for name in CRITERIA},
            ),
            workspace_root=str(self.workspace),
        )
        with self.assertRaises(ToolInvocationError) as caught:
            submit_vision_review(
                project_root=self.project_root,
                packet_path=packet["packet_path"],
                review=self.judgement(packet),
                workspace_root=str(self.workspace),
            )
        self.assertEqual("ui_vision_review_already_submitted", caught.exception.code)

    def test_an_unreadable_review_file_blocks_instead_of_vanishing(self) -> None:
        packet = self.build_packet()
        corrupt = Path(packet["packet_path"]).parent / "vision_review.corrupt.json"
        corrupt.write_text("{not json", encoding="utf-8")

        result = compare_ui_reference(
            project_root=self.project_root,
            reference_id="popup-available-v1",
            actual_image=str(self.capture),
            stability_image=str(self.capture),
            comparison_id="fixed-comparison",
            workspace_root=str(self.workspace),
            register_in_artifact_registry=False,
        )
        lane = result["acceptance_lanes"]["vision"]
        self.assertEqual("blocked", lane["status"])
        self.assertEqual("blocked", result["reference_acceptance"])

    def test_a_submitted_review_is_picked_up_by_the_next_comparison(self) -> None:
        packet = self.build_packet()
        submitted = submit_vision_review(
            project_root=self.project_root,
            packet_path=packet["packet_path"],
            review=self.judgement(packet),
            workspace_root=str(self.workspace),
        )
        self.assertTrue(submitted["succeeded"])

        result = compare_ui_reference(
            project_root=self.project_root,
            reference_id="popup-available-v1",
            actual_image=str(self.capture),
            stability_image=str(self.capture),
            comparison_id="fixed-comparison",
            workspace_root=str(self.workspace),
            register_in_artifact_registry=False,
        )
        lane = result["acceptance_lanes"]["vision"]
        self.assertEqual("passed", lane["status"])
        self.assertEqual(1, lane["judges"])
        self.assertEqual("required", lane["requirement"])
        self.assertEqual("passed", result["reference_acceptance"])

    def test_a_review_of_a_stale_capture_does_not_count(self) -> None:
        packet = self.build_packet()
        packet_path = packet["packet_path"]
        submit_vision_review(
            project_root=self.project_root,
            packet_path=packet_path,
            review=self.judgement(packet),
            workspace_root=str(self.workspace),
        )
        changed = write_image(self.captures / "candidate.png", solid(120, 240, (41, 80, 160, 255)))

        result = compare_ui_reference(
            project_root=self.project_root,
            reference_id="popup-available-v1",
            actual_image=str(changed),
            stability_image=str(changed),
            comparison_id="fixed-comparison",
            workspace_root=str(self.workspace),
            register_in_artifact_registry=False,
        )
        lane = result["acceptance_lanes"]["vision"]
        self.assertEqual("blocked", lane["status"])
        self.assertEqual("invalid_review_submitted", lane["blocked_reason"])
        self.assertIn("vision_packet_stale", lane["reviews"][0]["errors"])

    def test_a_failing_review_fails_a_pixel_identical_capture(self) -> None:
        packet = self.build_packet()
        criteria = {name: {"score": 3, "observation": "ok"} for name in CRITERIA}
        criteria["imagery"] = {"score": 1, "observation": "placeholder art instead of the final icon"}
        submit_vision_review(
            project_root=self.project_root,
            packet_path=packet["packet_path"],
            review=self.judgement(packet, criteria=criteria),
            workspace_root=str(self.workspace),
        )
        result = compare_ui_reference(
            project_root=self.project_root,
            reference_id="popup-available-v1",
            actual_image=str(self.capture),
            stability_image=str(self.capture),
            comparison_id="fixed-comparison",
            workspace_root=str(self.workspace),
            register_in_artifact_registry=False,
        )
        self.assertEqual("passed", result["visual_verdict"])
        self.assertEqual("failed", result["reference_acceptance"])
        self.assertEqual("vision_contradicts_similarity", result["lane_disagreement"]["code"])

    def test_numeric_evidence_is_disclosed_only_on_request(self) -> None:
        packet = self.build_packet(include_numeric_evidence=True)
        self.assertEqual("numeric_scores_disclosed", packet["attention"]["anchoring"])

    def test_a_stored_review_renormalizes_to_the_same_verdict(self) -> None:
        packet = self.build_packet()
        submitted = submit_vision_review(
            project_root=self.project_root,
            packet_path=packet["packet_path"],
            review=self.judgement(packet),
            workspace_root=str(self.workspace),
        )
        stored = json.loads(Path(submitted["stored_review_path"]).read_text(encoding="utf-8"))
        reloaded = normalize_vision_review(
            stored["vision_review"],
            policy=packet["policy"],
            expected_packet_hash=packet["packet_hash"],
        )
        self.assertEqual(submitted["review"]["verdict"], reloaded["verdict"])
        self.assertEqual([], reloaded["errors"])


class CrossLanguageContractTests(unittest.TestCase):
    """The ui_click step spans both languages; nothing at runtime cross-checks the two."""

    def read(self, relative: str) -> str:
        return (EDITOR_ROOT / relative).read_text(encoding="utf-8")

    def test_the_interaction_schema_version_matches_between_python_and_csharp(self) -> None:
        text = self.read("Core/XUUnityLightMcpUiReadModels.cs")
        match = re.search(r'InteractionSchemaVersion\s*=\s*"([^"]+)"', text)
        self.assertIsNotNone(match)
        self.assertEqual(UI_INTERACTION_SCHEMA_VERSION, match.group(1))

    def test_the_step_kind_matches_between_python_and_csharp(self) -> None:
        text = self.read("Core/XUUnityLightMcpUiReadModels.cs")
        match = re.search(r'InteractionStepKind\s*=\s*"([^"]+)"', text)
        self.assertIsNotNone(match)
        kind = match.group(1)
        step_schema = server_specs.SCENARIO_STEP_SCHEMA["properties"]
        self.assertIn(kind, step_schema["kind"]["enum"])
        self.assertIn(kind, step_schema["operation"]["enum"])

    def test_the_ui_read_step_kinds_match_between_python_and_csharp(self) -> None:
        text = self.read("Core/XUUnityLightMcpUiReadModels.cs")
        step_schema = server_specs.SCENARIO_STEP_SCHEMA["properties"]
        for constant, expected in (("ExistsStepKind", "ui_exists"), ("GetTextStepKind", "ui_get_text")):
            with self.subTest(kind=expected):
                match = re.search(rf'{constant}\s*=\s*"([^"]+)"', text)
                self.assertIsNotNone(match)
                self.assertEqual(expected, match.group(1))
                self.assertIn(expected, step_schema["kind"]["enum"])
                self.assertIn(expected, step_schema["operation"]["enum"])

    def test_the_step_is_dispatched_and_validated_in_the_editor_package(self) -> None:
        dispatcher = self.read("Helpers/XUUnityLightMcpScenarioStepDispatcher.cs")
        validator = self.read("Helpers/XUUnityLightMcpScenarioValidator.cs")
        self.assertIn("XUUnityLightMcpUiRead.InteractionStepKind", dispatcher)
        self.assertIn("ProcessUiClickStep", dispatcher)
        self.assertIn("XUUnityLightMcpUiRead.InteractionStepKind", validator)

    def test_the_step_requires_explicit_approval_in_both_layers(self) -> None:
        handler = self.read("Helpers/XUUnityLightMcpScenarioUiInteractionStepHandler.cs")
        validator = self.read("Helpers/XUUnityLightMcpScenarioValidator.cs")
        self.assertIn("ui_click_approval_required", handler)
        self.assertIn("ui_click_approval_required", validator)
        self.assertFalse(server_specs.SCENARIO_STEP_SCHEMA["properties"]["approve"]["default"])

    def test_the_step_handler_lives_in_the_core_assembly_and_calls_the_click_by_name(self) -> None:
        handler_path = EDITOR_ROOT / "Helpers" / "XUUnityLightMcpScenarioUiInteractionStepHandler.cs"
        self.assertTrue(handler_path.is_file())
        self.assertTrue(handler_path.with_suffix(".cs.meta").is_file())
        text = handler_path.read_text(encoding="utf-8")
        self.assertIn('"unity.ui.click"', text)
        self.assertNotIn("UnityEngine.UI", text)

    def test_the_click_operation_reports_point_of_use_liveness_itself(self) -> None:
        text = self.read("Ugui/XUUnityLightMcpUiClickOperation.cs")
        self.assertIn("XUUnityLightMcpPlayModeStateOperation.PopulateLivenessEvidence(payload)", text)
        self.assertNotIn("CurrentPlayModeState()", text)

    def test_the_click_operation_ranks_observable_effect_above_delivery(self) -> None:
        operation = self.read("Ugui/XUUnityLightMcpUiClickOperation.cs")
        self.assertIn("XUUnityLightMcpUiClickTreeWatch.Finalize(payload);", operation)
        self.assertNotIn("payload.success = payload.delivered;", operation)
        text = self.read("Helpers/XUUnityLightMcpUiClickTreeWatch.cs")

        self.assertIn("payload.effective = payload.delivered && payload.state_changed", text)
        self.assertIn('"delivered_no_observable_effect"', text)
        self.assertIn('"ui_click_no_state_change"', text)
        self.assertNotIn("payload.success = payload.delivered;", text)

    def test_scenario_click_preserves_search_budget_and_truncation_evidence(self) -> None:
        handler = self.read("Helpers/XUUnityLightMcpScenarioUiInteractionStepHandler.cs")

        self.assertIn("maxDepth = step.maxDepth > 0", handler)
        self.assertIn("maxNodes = step.maxNodes > 0", handler)
        self.assertIn("search_truncation_reason = click.search_truncation_reason", handler)
        self.assertEqual(12, server_specs.SCENARIO_STEP_SCHEMA["properties"]["maxDepth"]["default"])
        self.assertEqual(500, server_specs.SCENARIO_STEP_SCHEMA["properties"]["maxNodes"]["default"])

    def test_the_new_tools_are_host_only(self) -> None:
        for name in ("unity_ui_vision_packet", "unity_ui_vision_submit", "unity_ui_interaction_validate"):
            self.assertIn(name, server_specs.TOOLS)
            self.assertNotIn("bridgeOperation", server_specs.TOOLS[name])

    def test_the_vision_schema_version_is_declared_on_the_packet_tool(self) -> None:
        description = server_specs.TOOLS["unity_ui_vision_packet"]["description"]
        self.assertIn(UI_VISION_SCHEMA_VERSION.removeprefix("xuunity."), description)


if __name__ == "__main__":
    unittest.main()
