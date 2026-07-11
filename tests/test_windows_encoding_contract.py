"""UTF-8 encoding contract for Windows hosts.

Windows defaults piped stdio and subprocess text decoding to the ANSI/OEM
codepage (cp1251/cp866 on RU hosts). That killed the MCP stdio loop on a
Cyrillic projectRoot, broke editor detection when process command lines
contained non-ASCII paths, and produced ANSI-encoded plan files that
setup-apply then refused. These tests pin the fixes:

- every subprocess text call in templates/ declares utf-8 + errors=replace;
- entrypoints reconfigure stdio to utf-8 and default PYTHONUTF8=1;
- launcher flavors export PYTHONUTF8;
- manifest edits are explicit utf-8;
- the UPM ``file:`` dependency value is forward-slash on every host and
  degrades to an absolute path across drives.
"""

import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"

if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_core
import server_launcher


def iter_subprocess_text_calls(text: str):
    for match in re.finditer(r"subprocess\.(run|Popen|check_output|check_call)\(", text):
        depth = 0
        end = match.start()
        for index in range(match.end() - 1, len(text)):
            char = text[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        yield match.start(), text[match.start():end + 1]


class SubprocessEncodingSweepTest(unittest.TestCase):
    def test_every_text_subprocess_call_declares_utf8(self):
        offenders = []
        sources = sorted(TEMPLATES_DIR.glob("*.py"))
        sources.append(REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.py")
        for source in sources:
            text = source.read_text(encoding="utf-8")
            for offset, call in iter_subprocess_text_calls(text):
                if "text=True" not in call and "universal_newlines=True" not in call:
                    continue
                if "encoding=" in call:
                    continue
                line = text[:offset].count("\n") + 1
                offenders.append(f"{source.name}:{line}")
        self.assertEqual(
            offenders,
            [],
            "subprocess text decoding must not depend on the host ANSI codepage: "
            + ", ".join(offenders),
        )


class StdioReconfigureTest(unittest.TestCase):
    def test_reconfigure_skips_streams_without_reconfigure(self):
        fake_out = io.StringIO()
        with mock.patch.object(sys, "stdin", fake_out), \
                mock.patch.object(sys, "stdout", fake_out), \
                mock.patch.object(sys, "stderr", fake_out):
            server_core.reconfigure_stdio_utf8()

    def test_reconfigure_requests_utf8_replace(self):
        stream = mock.Mock()
        with mock.patch.object(sys, "stdin", stream), \
                mock.patch.object(sys, "stdout", stream), \
                mock.patch.object(sys, "stderr", stream):
            server_core.reconfigure_stdio_utf8()
        stream.reconfigure.assert_called_with(encoding="utf-8", errors="replace")
        self.assertEqual(stream.reconfigure.call_count, 3)

    def test_entrypoints_invoke_reconfigure(self):
        server_main = (TEMPLATES_DIR / "server.py").read_text(encoding="utf-8")
        launcher_main = (TEMPLATES_DIR / "server_launcher.py").read_text(encoding="utf-8")
        refresh_main = (REPO_ROOT / "run_installed_or_refresh_xuunity_mcp.py").read_text(encoding="utf-8")
        for name, text in (
            ("server.py", server_main),
            ("server_launcher.py", launcher_main),
            ("run_installed_or_refresh_xuunity_mcp.py", refresh_main),
        ):
            self.assertIn("reconfigure_stdio_utf8()", text, name)


class LauncherPythonUtf8Test(unittest.TestCase):
    LAUNCHERS = (
        "xuunity_light_unity_mcp.sh",
        "xuunity_light_unity_mcp.ps1",
        "xuunity_light_unity_mcp.cmd",
        "run_installed_or_refresh_xuunity_mcp.sh",
        "run_installed_or_refresh_xuunity_mcp.cmd",
        "templates/run.sh",
        "templates/run.ps1",
        "templates/run.cmd",
    )

    def test_all_launcher_flavors_default_pythonutf8(self):
        for relative in self.LAUNCHERS:
            text = (REPO_ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("PYTHONUTF8", text, relative)


class ManifestEncodingTest(unittest.TestCase):
    def test_manifest_update_round_trips_non_ascii_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(
                json.dumps({"dependencies": {"com.example.локализация": "1.0.0"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            server_launcher.update_manifest_dependency(str(manifest), "file:../pkg")
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(data["dependencies"]["com.xuunity.light-mcp"], "file:../pkg")
            self.assertIn("com.example.локализация", data["dependencies"])


class FileDependencyFormatTest(unittest.TestCase):
    def test_windows_relpath_renders_forward_slashes(self):
        with mock.patch.object(server_launcher.os.path, "relpath", return_value=r"..\..\AIRoot\pkg"):
            value = server_launcher.format_package_file_dependency("ignored", "ignored")
        self.assertEqual(value, "file:../../AIRoot/pkg")

    def test_cross_drive_relpath_falls_back_to_absolute_posix(self):
        with mock.patch.object(
            server_launcher.os.path,
            "relpath",
            side_effect=ValueError("path is on mount 'D:', start on mount 'C:'"),
        ):
            value = server_launcher.format_package_file_dependency(
                str(REPO_ROOT / "packages" / "com.xuunity.light-mcp"), "ignored"
            )
        self.assertTrue(value.startswith("file:"))
        self.assertNotIn("\\", value)
        self.assertTrue(value.endswith("packages/com.xuunity.light-mcp"))


if __name__ == "__main__":
    unittest.main()
