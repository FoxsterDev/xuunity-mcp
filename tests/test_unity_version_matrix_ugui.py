"""The version matrix gives created projects uGUI, so the EditModeUgui self-tests run on 6000.x too."""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_SCRIPT = REPO_ROOT / "scripts" / "testing" / "run_unity_version_matrix.sh"


class UnityVersionMatrixUguiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matrix = MATRIX_SCRIPT.read_text(encoding="utf-8")

    def test_ugui_is_added_after_the_project_is_created_and_before_the_package_install(self) -> None:
        create_at = self.matrix.index('if ! create_project_if_needed "$unity_version"')
        add_at = self.matrix.index('[[ "$ADD_UGUI" == "true" ]] && ! add_ugui_dependencies "$unity_version" "$project_root"')
        install_at = self.matrix.index('if ! install_mcp_package "$project_root"')
        self.assertLess(create_at, add_at)
        self.assertLess(add_at, install_at)

    def test_the_step_goes_through_the_scaffold_helper(self) -> None:
        self.assertIn('SCAFFOLD_SCRIPT="$SCRIPT_DIR/scaffold_unity_ci_project.py"', self.matrix)
        self.assertIn("--add-ugui-to-existing", self.matrix)
        self.assertTrue((REPO_ROOT / "scripts" / "testing" / "scaffold_unity_ci_project.py").is_file())

    def test_ugui_is_on_by_default_and_no_ugui_opts_out(self) -> None:
        self.assertIn('ADD_UGUI="true"\n', self.matrix)
        self.assertIn('    --no-ugui)\n      ADD_UGUI="false"\n', self.matrix)


if __name__ == "__main__":
    unittest.main()
