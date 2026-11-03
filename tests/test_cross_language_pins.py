"""Pins for the values Python and C# must agree on by string.

The two existing contract test classes hold the `ui_click` interaction contract and the uGUI/prefab
read surface hard. Everything outside those bands was unheld: operation names, enum string values,
bridge error codes and the file-IPC path layout are each written independently on both sides, and a
rename on one side kept the whole suite green while breaking the seam. Each pin below names a value
that appears in both languages and asserts they still match.

The failure modes these guard are not compile errors. A renamed `playmode_state` value makes every
delivered click read as Edit-mode delivery forever; a renamed `targetKind` value silently widens a
scoped query to the whole scene and returns a match from a different subtree; a renamed inbox
directory makes the host write requests the editor never reads.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent
TEMPLATES_DIR = REPO_ROOT / "templates"
for entry in (TEMPLATES_DIR, TESTS_DIR):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import server_bridge_paths
import server_operation_evidence
import server_project_actions
import server_specs
from server_ui_interaction import RUNTIME_PLAYMODE_STATES

EDITOR_ROOT = REPO_ROOT / "packages" / "com.xuunity.light-mcp" / "Editor"


def editor_sources() -> list[Path]:
    return sorted(EDITOR_ROOT.rglob("*.cs"))


def editor_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in editor_sources())


class PlayModeStateVocabularyTest(unittest.TestCase):
    """`playmode_state` is produced in four places in C# and consumed in five in Python."""

    EXPECTED = ("edit", "playing", "paused", "transitioning")

    def test_every_state_python_branches_on_exists_in_the_editor(self) -> None:
        text = editor_text()
        for state in self.EXPECTED:
            self.assertIn(
                f'"{state}"',
                text,
                f"Python reads playmode_state '{state}' but no editor source emits it",
            )

    def test_the_runtime_states_are_the_ones_python_treats_as_running(self) -> None:
        self.assertEqual(("playing", "paused"), tuple(RUNTIME_PLAYMODE_STATES))
        for state in RUNTIME_PLAYMODE_STATES:
            self.assertIn(state, self.EXPECTED)

    def test_edit_is_not_a_runtime_state(self) -> None:
        # Edit-mode delivery proves the wiring, not the user path.
        self.assertNotIn("edit", RUNTIME_PLAYMODE_STATES)


class TargetKindVocabularyTest(unittest.TestCase):
    """An unrecognised targetKind falls back to the whole active scene, so a rename is a silent
    false positive rather than an error."""

    def test_the_kinds_the_tool_schema_offers_are_declared_in_the_editor(self) -> None:
        declared: set[str] = set()
        for spec in server_specs.TOOLS.values():
            schema = spec.get("inputSchema") or {}
            for name, prop in (schema.get("properties") or {}).items():
                if name == "targetKind":
                    declared.update(str(value) for value in (prop.get("enum") or []))
        self.assertTrue(declared, "no tool declares a targetKind enum")

        text = editor_text()
        for kind in sorted(declared):
            self.assertIn(
                f'"{kind}"',
                text,
                f"tool schemas offer targetKind '{kind}' but no editor source declares it",
            )


class UiDiagnosticVocabularyTest(unittest.TestCase):
    """Values Python branches on to decide a node is unhealthy. If C# renames one, the lane reads
    the node as fine and degrades to not_evaluated instead of failing."""

    CLIP_STATES = ("fully_clipped", "partially_clipped", "not_clipped", "not_evaluated")
    MATERIAL_STATES = ("unresolved", "font_without_material", "target_graphic_missing")
    FONT_STATES = ("resolved", "unresolved")

    def test_clip_material_and_font_states_exist_on_both_sides(self) -> None:
        text = editor_text()
        explain = (TEMPLATES_DIR / "server_ui_region_explain.py").read_text(encoding="utf-8")
        for group in (self.CLIP_STATES, self.MATERIAL_STATES, self.FONT_STATES):
            for value in group:
                self.assertIn(f'"{value}"', text, f"editor sources no longer emit '{value}'")
        for value in ("fully_clipped", "partially_clipped"):
            self.assertIn(value, explain, f"the explanation lane no longer reads '{value}'")
        for value in self.MATERIAL_STATES:
            self.assertIn(value, explain, f"the explanation lane no longer reads '{value}'")


class BridgeErrorCodeTest(unittest.TestCase):
    """The only degradation signal a caller gets for a constraint-gated operation."""

    CODES = ("operation_unavailable", "tool_unsupported", "bridge_request_failed", "unknown_bridge_error")

    def test_the_documented_refusal_codes_are_still_emitted(self) -> None:
        text = editor_text()
        for code in self.CODES:
            self.assertIn(f'"{code}"', text, f"no editor source emits the '{code}' refusal")


class FileIpcLayoutTest(unittest.TestCase):
    """Both sides build this tree from independent literals; nothing compared them."""

    def editor_layout(self) -> dict[str, tuple[str, ...]]:
        """Resolve each `X => Path.Combine(...)` to its segments below the project root.

        The expressions nest by symbol, so the literals alone are not the whole path."""

        source = (EDITOR_ROOT / "Core" / "XUUnityLightMcpFileIpcPaths.cs").read_text(encoding="utf-8")
        definitions = {
            name: [token.strip() for token in args.split(",")]
            for name, args in re.findall(r"(\w+)\s*=>\s*Path\.Combine\(([^;]+)\);", source)
        }

        resolved: dict[str, tuple[str, ...]] = {}

        def resolve(name: str) -> tuple[str, ...]:
            if name in resolved:
                return resolved[name]
            if name == "ProjectRootPath":
                return ()
            segments: list[str] = []
            for token in definitions.get(name, []):
                literal = re.fullmatch(r'"([^"]*)"', token)
                if literal:
                    segments.append(literal.group(1))
                else:
                    segments.extend(resolve(token))
            resolved[name] = tuple(segments)
            return resolved[name]

        for name in definitions:
            resolve(name)
        return resolved

    def test_the_python_layout_matches_the_editor_layout(self) -> None:
        layout = self.editor_layout()
        project = Path("/project")
        cases = {
            "RootPath": server_bridge_paths.bridge_root(project),
            "ConfigDirectory": server_bridge_paths.bridge_config_path(project).parent,
            "StateDirectory": server_bridge_paths.bridge_state_path(project).parent,
            "InboxDirectory": server_bridge_paths.inbox_dir(project),
            "OutboxDirectory": server_bridge_paths.outbox_dir(project),
            "CapturesDirectory": server_bridge_paths.captures_dir(project),
            "ScenariosDirectory": server_bridge_paths.scenarios_dir(project),
            "LogsDirectory": server_bridge_paths.logs_dir(project),
            "ScenarioResultsDirectory": server_bridge_paths.scenario_results_dir(project),
        }
        for name, python_path in cases.items():
            self.assertIn(name, layout, f"{name} is no longer a Path.Combine expression")
            self.assertEqual(
                python_path.relative_to(project).parts,
                layout[name],
                f"{name} disagrees with the Python layout for the same directory",
            )

    def test_the_scenario_results_directory_agrees(self) -> None:
        source = (EDITOR_ROOT / "Core" / "XUUnityLightMcpFileIpcPaths.cs").read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r'ScenarioResultsDirectory\s*=>\s*Path\.Combine\(ScenariosDirectory,\s*"results"\)',
        )
        project = Path("/project")
        self.assertEqual(
            ("Library", "XUUnityLightMcp", "scenarios", "results"),
            server_bridge_paths.scenario_results_dir(project).relative_to(project).parts,
        )

    def test_the_journal_directory_agrees(self) -> None:
        project = Path("/project")
        self.assertEqual(
            ("Library", "XUUnityLightMcp", "journal", "requests"),
            server_bridge_paths.request_journal_dir(project).relative_to(project).parts,
        )
        self.assertIn(
            'JournalDirectory => Path.Combine(RootPath, "journal")',
            (EDITOR_ROOT / "Core" / "XUUnityLightMcpFileIpcPaths.cs").read_text(encoding="utf-8"),
        )


class BridgeOperationCoverageTest(unittest.TestCase):
    """Every declared bridgeOperation, not only the ui/prefab ones.

    The existing check early-continues on any operation that is not `unity.ui.*` or
    `unity.prefab.*`, which left most of the surface unverified."""

    def editor_registered_operations(self) -> set[str]:
        registered: set[str] = set()
        registry = EDITOR_ROOT / "Core" / "XUUnityLightMcpOperationRegistry.cs"
        registered.update(re.findall(r'\{\s*"([a-z0-9_.]+)"\s*,\s*new ', registry.read_text(encoding="utf-8")))
        # Satellite and test-framework assemblies register themselves at load time and declare the
        # name on the operation class, under more than one constant name.
        for source in editor_sources():
            text = source.read_text(encoding="utf-8")
            registered.update(
                re.findall(r'(?:RegisteredOperationName|OperationName)\s*=\s*"([a-z0-9_.]+)"', text)
            )
        return registered

    def test_every_declared_editor_operation_resolves(self) -> None:
        registered = self.editor_registered_operations()
        declared = {
            name: spec["bridgeOperation"]
            for name, spec in server_specs.TOOLS.items()
            if str(spec.get("bridgeOperation") or "").startswith("unity.")
        }
        self.assertGreater(len(declared), 20, "the declared editor surface shrank unexpectedly")

        missing = sorted(
            f"{name} -> {operation}"
            for name, operation in declared.items()
            if operation not in registered
        )
        self.assertEqual([], missing, "host tools point at operations no editor source registers")

    def test_host_executed_operations_are_not_expected_in_the_editor(self) -> None:
        """`bridgeOperation` also names host-side work, which the editor must not claim to own."""

        registered = self.editor_registered_operations()
        host_side = sorted(
            str(spec["bridgeOperation"])
            for spec in server_specs.TOOLS.values()
            if str(spec.get("bridgeOperation") or "").startswith("host.")
        )
        self.assertTrue(host_side, "no host-executed operation is declared any more")
        for operation in host_side:
            self.assertNotIn(operation, registered)

    def test_the_test_framework_operations_are_found(self) -> None:
        # These live on a differently named constant, which an earlier narrower helper missed.
        registered = self.editor_registered_operations()
        for operation in ("unity.tests.run_editmode", "unity.tests.run_playmode"):
            self.assertIn(operation, registered)


class BuildPipelineNoisePatternTest(unittest.TestCase):
    """`unity_console_grep` suppresses build-pipeline chatter on two independent lanes.

    The console-buffer lane filters in C#, the Editor.log lane filters in Python. If the two patterns
    drift, the same grep suppresses different lines depending on which source the caller picked, and a
    real defect can be visible on one lane and hidden on the other.
    """

    def test_both_lanes_use_the_same_pattern(self) -> None:
        import server_health

        noise_source = (EDITOR_ROOT / "Core" / "XUUnityLightMcpConsoleNoise.cs").read_text(
            encoding="utf-8"
        )
        match = re.search(
            r"BuildPipelineProgressPattern\s*=\s*\n?\s*@\"(?P<pattern>.+?)\";",
            noise_source,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "the editor pattern constant could not be read")
        self.assertEqual(
            match.group("pattern"),
            server_health.BUILD_PIPELINE_PROGRESS_PATTERN,
            "the C# console lane and the Python Editor.log lane must suppress the same lines",
        )

    def test_the_pattern_suppresses_the_observed_noise_and_keeps_real_findings(self) -> None:
        import server_health

        # The feature keyword is the point: a compile job named after the feature makes every
        # CopyFiles line match a grep for it, which is how 159 matches hid an answer of zero.
        for noisy in (
            "CopyFiles Library/Bee/artifacts/RewardPopup-Android/RewardPopup.dll",
            "  CopyDirs Library/Bee/artifacts",
            "[12/431 ...] CopyFiles something",
        ):
            self.assertIsNotNone(
                server_health.BUILD_PIPELINE_PROGRESS.search(noisy),
                noisy,
            )
        for real in (
            "NullReferenceException: RewardPopupPresenter.Show",
            "Assets/Scripts/RewardPopup.cs(42,9): error CS0103",
            "RewardPopup opened",
        ):
            self.assertIsNone(server_health.BUILD_PIPELINE_PROGRESS.search(real), real)


class ProjectActionExpansionParityTest(unittest.TestCase):
    """The project_action step expansion is written twice, in two languages.

    `expand_project_action_hook_step` in Python and `XUUnityLightMcpProjectActionStepBuilder` in C#
    both encode the step-id suffixes, the generated refresh step and the dependsOn wiring, and the
    editor normalizer runs on every scenario a client sends straight to the bridge. A value that
    drifts on one side changes the scenario a caller gets depending on which lane expanded it, and
    the Unity package suite cannot run in hosted CI, so these pins are the only cross-lane guard.
    """

    def builder_source(self) -> str:
        return (
            EDITOR_ROOT / "Helpers" / "XUUnityLightMcpProjectActionStepBuilder.cs"
        ).read_text(encoding="utf-8")

    def test_the_generated_step_id_suffixes_match(self) -> None:
        source = self.builder_source()

        self.assertIn(
            f'const string CurrencySuffix = "{server_project_actions.PROJECT_ACTION_CURRENCY_SUFFIX}";',
            source,
        )
        self.assertIn(
            f'const string RefreshSuffix = "{server_project_actions.PROJECT_ACTION_REFRESH_SUFFIX}";',
            source,
        )

    def test_the_inert_input_keys_dropped_from_the_hook_step_match(self) -> None:
        source = self.builder_source()
        declared = source.split("ProjectActionStepKeys", 1)[1].split("};", 1)[0]
        editor_keys = set(re.findall(r'"([A-Za-z]+)"', declared))

        self.assertEqual(set(server_project_actions.PROJECT_ACTION_STEP_KEYS), editor_keys)

    def test_the_generated_refresh_step_flags_match(self) -> None:
        source = self.builder_source()
        refresh = source.split("static LightJsonNode BuildRefreshStep", 1)[1].split("return refreshStep;", 1)[0]

        self.assertIn('refreshStep.Object["kind"] = LightJsonNode.String("project_refresh")', refresh)
        self.assertIn('"forceAssetRefresh"', refresh)
        self.assertIn("BoolValue = true", refresh)
        self.assertIn('"resolvePackages"', refresh)
        self.assertIn('"rerunHealthProbe"', refresh)
        self.assertIn('NumberValue = "180"', refresh)

    def test_the_python_expansion_emits_the_shape_the_editor_emits(self) -> None:
        raw = server_project_actions.parse_project_actions_yaml(
            "\n".join(
                [
                    "schemaVersion: xuunity.project-actions.v1",
                    "project: FakeProject",
                    "actions:",
                    "  localization.scan:",
                    "    hookName: sample.localization",
                    "    requiresFreshAssets: true",
                ]
            )
        )
        project_root = Path("/tmp/FakeProject")
        catalog = server_project_actions.normalize_project_action_catalog(
            raw,
            project_root=project_root,
            catalog_path=project_root / "project_actions.yaml",
        )
        steps = server_project_actions.normalize_project_action_steps(
            catalog=catalog,
            steps=[
                {
                    "stepId": "scan",
                    "kind": "project_action",
                    "actionId": "localization.scan",
                    "allowMutating": True,
                    "catalogPath": "ignored.yaml",
                    "dependsOn": ["prepare"],
                    "runIfStepPassed": ["prepare"],
                    "payload": {},
                }
            ],
            step_group="steps",
        )
        shapes = [
            {key: value for key, value in step.items() if key != "hookPayloadJson"}
            for step in steps
        ]

        self.assertEqual(
            [
                {
                    "stepId": "scan__refresh_assets",
                    "kind": "project_refresh",
                    "forceAssetRefresh": True,
                    "resolvePackages": False,
                    "rerunHealthProbe": False,
                    "timeoutSeconds": 180.0,
                    "dependsOn": ["prepare"],
                    "runIfStepPassed": ["prepare"],
                },
                {
                    "stepId": "scan__currency",
                    "kind": "project_action_currency",
                    "actionId": "localization.scan",
                    "requiresFreshAssets": True,
                    "assetRefreshStepId": "scan__refresh_assets",
                    "dependsOn": ["scan__refresh_assets"],
                },
                {
                    "stepId": "scan",
                    "kind": "project_defined_hook",
                    "hookName": "sample.localization",
                    "mutationSettlePolicy": "",
                    "dependsOn": ["scan__currency"],
                },
            ],
            shapes,
        )



class TestEnvironmentFieldsTest(unittest.TestCase):
    """The host projection whitelists test_environment keys, so a C# rename silently drops the field."""

    MODELS = EDITOR_ROOT / "Core" / "XUUnityLightMcpConsoleSceneTestModels.cs"

    def class_body(self, text: str, name: str) -> str:
        match = re.search(r"class " + re.escape(name) + r"\s*\{(.*?)\n\s*\}", text, re.S)
        self.assertIsNotNone(match, f"{name} is missing from the editor models")
        return match.group(1)

    def test_the_editor_model_declares_exactly_the_projected_fields(self) -> None:
        text = self.MODELS.read_text(encoding="utf-8")
        body = self.class_body(text, "XUUnityLightMcpTestEnvironment")
        declared = tuple(re.findall(r"public\s+\w+\s+(\w+)\s*[;=]", body))
        self.assertEqual(server_operation_evidence.TEST_ENVIRONMENT_FIELDS, declared)
        for owner in ("XUUnityLightMcpTestsPayload", "XUUnityLightMcpPersistedTestRunState"):
            self.assertIn(
                "public XUUnityLightMcpTestEnvironment test_environment",
                self.class_body(text, owner),
                f"{owner} no longer carries test_environment",
            )

    def test_the_capture_statuses_and_preset_kinds_exist_in_the_editor(self) -> None:
        text = editor_text()
        for value in (
            "captured",
            "game_view_not_rendered",
            "no_game_view",
            "unavailable",
            "fixed_resolution",
            "aspect_ratio",
            "free",
            "unknown",
            "request_start",
        ):
            self.assertIn(f'"{value}"', text, f"no editor source emits test_environment value '{value}'")


class ConsoleErrorClassificationVocabularyTest(unittest.TestCase):
    """The host re-projects console error samples by whitelist, so a C# rename silently drops the evidence."""

    MODELS = EDITOR_ROOT / "Core" / "XUUnityLightMcpConsoleSceneTestModels.cs"
    ATTRIBUTION = EDITOR_ROOT / "TestFramework" / "Helpers" / "XUUnityLightMcpTestLogAttribution.cs"

    def class_body(self, text: str, name: str) -> str:
        match = re.search(r"class " + re.escape(name) + r"\s*\{(.*?)\n\s*\}", text, re.S)
        self.assertIsNotNone(match, f"{name} is missing from the editor models")
        return match.group(1)

    def constant(self, text: str, name: str) -> str:
        match = re.search(r"const\s+\w+\s+" + re.escape(name) + r"\s*=\s*([^;]+);", text)
        self.assertIsNotNone(match, f"constant {name} is missing from the editor models")
        return match.group(1).strip()

    def test_the_sample_model_declares_exactly_the_projected_fields(self) -> None:
        body = self.class_body(self.MODELS.read_text(encoding="utf-8"), "XUUnityLightMcpConsoleErrorSample")
        declared = tuple(re.findall(r"public\s+\w+\s+(\w+)\s*[;=]", body))
        self.assertEqual(server_operation_evidence.CONSOLE_ERROR_SAMPLE_FIELDS, declared)

    def test_limits_classes_and_bases_match_the_host(self) -> None:
        text = self.MODELS.read_text(encoding="utf-8")
        self.assertEqual(str(server_operation_evidence.CONSOLE_ERROR_SAMPLE_LIMIT), self.constant(text, "MaxSamples"))
        self.assertEqual(
            str(server_operation_evidence.CONSOLE_ERROR_SAMPLE_MESSAGE_LIMIT), self.constant(text, "MaxSampleMessageChars")
        )
        self.assertEqual(
            str(server_operation_evidence.CONSOLE_ERROR_SAMPLE_ACTIVE_TEST_LIMIT),
            self.constant(text, "MaxSampleActiveTestChars"),
        )
        literals = set(re.findall(r'const\s+string\s+\w+\s*=\s*"([^"]*)"', text))
        for value in server_operation_evidence.CONSOLE_ERROR_SAMPLE_CLASSES + server_operation_evidence.CONSOLE_ERROR_CLASSIFICATION_BASES:
            self.assertIn(value, literals, f"no editor constant emits console error value '{value}'")
        attribution = self.ATTRIBUTION.read_text(encoding="utf-8")
        for value in server_operation_evidence.CONSOLE_ERROR_SAMPLE_TYPES:
            self.assertIn(f'"{value}"', attribution, f"no editor source emits console error sample type '{value}'")

    def test_payload_and_persisted_state_carry_the_fields_the_host_reads(self) -> None:
        text = self.MODELS.read_text(encoding="utf-8")
        payload = self.class_body(text, "XUUnityLightMcpTestsPayload")
        for field in (
            "console_error_expected_by_test_count",
            "console_error_not_expected_count",
            "console_error_classification_basis",
            "console_error_samples",
        ):
            self.assertRegex(payload, r"public\s+[\w<>]+\s+" + field + r"\b")
        persisted = self.class_body(text, "XUUnityLightMcpPersistedTestRunState")
        for field in (
            "console_error_samples",
            "console_error_expected_by_test_count",
            "console_error_expected_by_test_count_in_session",
            "console_error_expected_by_test_counter_session_id",
            "console_error_not_expected_recorded_count",
            "console_error_classification_basis",
            "console_error_count_at_completion",
            "console_error_count_trust_class_at_completion",
            "console_error_not_expected_count_at_completion",
        ):
            self.assertRegex(persisted, r"public\s+[\w<>]+\s+" + field + r"\b")


if __name__ == "__main__":
    unittest.main()
