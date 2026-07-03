import unittest
from pathlib import Path


TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
SMOKE_DIR = TEMPLATES_DIR / "smoke"


class SmokePayloadContractTests(unittest.TestCase):
    maxDiff = None

    def _assert_block_has_full_payload(self, filename: str, start: str, end: str) -> None:
        text = (SMOKE_DIR / filename).read_text(encoding="utf-8")
        start_index = text.find(start)
        self.assertNotEqual(-1, start_index, f"{filename}: start marker not found: {start}")
        end_index = text.find(end, start_index)
        self.assertNotEqual(-1, end_index, f"{filename}: end marker not found: {end}")
        block = text[start_index:end_index]
        self.assertIn("--include-full-payload", block, f"{filename}: {start}")

    def test_step_level_scenario_smokes_request_full_payload(self) -> None:
        """Smokes that inspect raw scenario steps must not parse compact verdicts."""

        for filename, start, end in [
            (
                "run_post_change_validation.sh",
                "run_step acceptance_scenario",
                'summarize_json \\\n  "acceptance-scenario"',
            ),
            (
                "run_post_change_validation.sh",
                "run_step contract_scenario",
                'summarize_json \\\n  "contract-scenario"',
            ),
            (
                "run_lifecycle_stress_suite.sh",
                "run_step background_contract_scenario",
                'summarize_json \\\n  "background-contract-scenario"',
            ),
            (
                "run_playmode_settled_state_regression.sh",
                '"$WRAPPER" request-scenario-run-and-wait',
                '>"$TMP_DIR/scenario.json"',
            ),
        ]:
            self._assert_block_has_full_payload(filename, start, end)

    def test_post_change_validation_emits_durable_phase_lines(self) -> None:
        text = (SMOKE_DIR / "run_post_change_validation.sh").read_text(encoding="utf-8")
        for phase in [
            "readiness",
            "compile matrix",
            "acceptance scenario",
            "contract scenario",
            "PlayMode/lifecycle checks",
            "auxiliary consistency checks",
            "cleanup/restore",
        ]:
            self.assertIn(f'emit_phase "{phase}"', text)
        self.assertIn('emit_heartbeat "cleanup_restore"', text)
        self.assertIn('emit_heartbeat "auxiliary_consistency_checks"', text)

    def test_post_change_validation_classifies_bridge_churn(self) -> None:
        text = (SMOKE_DIR / "run_post_change_validation.sh").read_text(encoding="utf-8")
        self.assertIn("non_blocking_churn", text)
        self.assertIn("actionable_churn", text)
        self.assertIn("churn_classification=", text)
        self.assertNotIn("high_bridge_generation_churn", text)


if __name__ == "__main__":
    unittest.main()
