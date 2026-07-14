import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_core
import server_editor_host
import server_host_platform


class WindowsHostHelperTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX host classification")
    def test_appdata_alone_does_not_select_windows_launcher_on_posix(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "APPDATA": "/forwarded/windows/appdata",
                "OS": "",
                "MSYSTEM": "",
                "XUUNITY_LIGHT_UNITY_MCP_LAUNCHER_NAME": "",
            },
            clear=False,
        ):
            self.assertFalse(server_core.is_windows_like_host())
            self.assertEqual("xuunity_light_unity_mcp.sh", server_core.launcher_command_name())

    def test_read_json_accepts_portable_plan_file_encodings(self) -> None:
        payload = {"action": "setup_plan", "projects": [{"project_root": "C:/Project"}]}

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            utf8 = root / "utf8.json"
            utf8_bom = root / "utf8-bom.json"
            utf16 = root / "utf16.json"
            utf8.write_bytes(json.dumps(payload).encode("utf-8"))
            utf8_bom.write_bytes(json.dumps(payload).encode("utf-8-sig"))
            utf16.write_bytes(json.dumps(payload).encode("utf-16"))

            self.assertEqual(payload, server_core.read_json(utf8))
            self.assertEqual(payload, server_core.read_json(utf8_bom))
            self.assertEqual(payload, server_core.read_json(utf16))

    def test_windows_tasklist_pid_match_is_exact(self) -> None:
        output = "\n".join(
            [
                "Unity.exe                  14321 Console",
                "Unity.exe                   4321 Console",
            ]
        )

        self.assertTrue(server_host_platform.windows_tasklist_contains_pid(output, 4321))
        self.assertFalse(server_host_platform.windows_tasklist_contains_pid(output, 321))

    def test_windows_tasklist_ignores_error_lines(self) -> None:
        output = "\n".join(
            [
                "ERROR: PID 4321 not found.",
                "INFO: No tasks are running which match the specified criteria.",
                "Image Name                     PID Session Name        Session#    Mem Usage",
                "========================= ======== ================ =========== ============",
            ]
        )

        self.assertFalse(server_host_platform.windows_tasklist_contains_pid(output, 4321))

    def test_windows_to_wsl_path_falls_back_without_wslpath(self) -> None:
        with (
            mock.patch.object(server_host_platform, "is_wsl", return_value=True),
            mock.patch.object(server_host_platform.subprocess, "run", side_effect=OSError("missing wslpath")),
        ):
            self.assertEqual(
                "/mnt/d/ProgramFiles/UnityHub/Editor/6000.3.2f1/Editor/Unity.exe",
                server_host_platform.windows_to_wsl_path(
                    r"D:\ProgramFiles\UnityHub\Editor\6000.3.2f1\Editor\Unity.exe"
                ),
            )

    def test_wsl_to_windows_path_falls_back_without_wslpath(self) -> None:
        with (
            mock.patch.object(server_host_platform, "is_wsl", return_value=True),
            mock.patch.object(server_host_platform.subprocess, "run", side_effect=OSError("missing wslpath")),
        ):
            self.assertEqual(
                r"D:\Development\Unity\_mtr\HumanFactory",
                server_host_platform.wsl_to_windows_path("/mnt/d/Development/Unity/_mtr/HumanFactory"),
            )

    def test_host_path_to_local_path_is_noop_outside_wsl(self) -> None:
        with mock.patch.object(server_host_platform, "is_wsl", return_value=False):
            self.assertEqual(
                r"D:\Development\Unity\_mtr\HumanFactory",
                server_host_platform.host_path_to_local_path(r"D:\Development\Unity\_mtr\HumanFactory"),
            )

    def test_configured_unity_editor_roots_keep_windows_drive_path_intact_under_wsl(self) -> None:
        with (
            mock.patch.object(server_editor_host, "is_wsl", return_value=True),
            mock.patch.object(server_editor_host, "host_path_to_local_path", side_effect=lambda value: f"converted:{value}"),
            mock.patch.dict(
                server_editor_host.os.environ,
                {"XUUNITY_UNITY_EDITOR_ROOTS": r"D:\ProgramFiles\UnityHub\Editor"},
                clear=False,
            ),
        ):
            roots = server_editor_host.configured_unity_editor_roots()

        self.assertEqual([Path(r"converted:D:\ProgramFiles\UnityHub\Editor")], roots)

    def test_configured_unity_editor_roots_split_windows_style_list_under_wsl(self) -> None:
        with (
            mock.patch.object(server_editor_host, "is_wsl", return_value=True),
            mock.patch.object(server_editor_host, "host_path_to_local_path", side_effect=lambda value: f"converted:{value}"),
            mock.patch.dict(
                server_editor_host.os.environ,
                {"XUUNITY_UNITY_EDITOR_ROOTS": r"C:\UnityHub\Editor;D:\ProgramFiles\UnityHub\Editor"},
                clear=False,
            ),
        ):
            roots = server_editor_host.configured_unity_editor_roots()

        self.assertEqual(
            [Path(r"converted:C:\UnityHub\Editor"), Path(r"converted:D:\ProgramFiles\UnityHub\Editor")],
            roots,
        )

    def test_configured_unity_editor_roots_split_posix_list_outside_wsl(self) -> None:
        with (
            mock.patch.object(server_editor_host, "is_wsl", return_value=False),
            mock.patch.object(server_editor_host.os, "pathsep", ":"),
            mock.patch.dict(
                server_editor_host.os.environ,
                {"XUUNITY_UNITY_EDITOR_ROOTS": "/opt/unity-a:/opt/unity-b"},
                clear=False,
            ),
        ):
            roots = server_editor_host.configured_unity_editor_roots()

        self.assertEqual([Path("/opt/unity-a"), Path("/opt/unity-b")], roots)

    def test_iter_candidate_installation_paths_finds_nonstandard_unityhub_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "ProgramFiles"
            unity_exe = root / "UnityHub" / "Editor" / "6000.3.2f1" / "Editor" / "Unity.exe"
            unity_exe.parent.mkdir(parents=True)
            unity_exe.write_text("", encoding="utf-8")

            with (
                mock.patch.object(server_editor_host, "host_platform_kind", return_value="linux"),
                mock.patch.object(server_editor_host, "is_wsl", return_value=True),
            ):
                candidates = server_editor_host.iter_candidate_installation_paths_from_root(root)

        self.assertIn(unity_exe, candidates)

    def test_normalize_unity_installation_path_supports_macos_app_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            unity_app = Path(tmp_dir) / "2022.3.60f1" / "Unity.app"
            unity_binary = unity_app / "Contents" / "MacOS" / "Unity"
            unity_binary.parent.mkdir(parents=True)
            unity_binary.write_text("", encoding="utf-8")

            with (
                mock.patch.object(server_editor_host, "host_platform_kind", return_value="macos"),
                mock.patch.object(server_editor_host, "is_wsl", return_value=False),
            ):
                self.assertEqual(unity_app.resolve(), server_editor_host.normalize_unity_installation_path(unity_app))
                self.assertEqual(unity_app.resolve(), server_editor_host.normalize_unity_installation_path(unity_binary))
                self.assertEqual("2022.3.60f1", server_editor_host.resolve_unity_app_version(unity_app))

    def test_normalize_unity_installation_path_supports_linux_editor_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            editor_root = Path(tmp_dir) / "6000.3.2f1"
            unity_binary = editor_root / "Editor" / "Unity"
            unity_binary.parent.mkdir(parents=True)
            unity_binary.write_text("", encoding="utf-8")

            with (
                mock.patch.object(server_editor_host, "host_platform_kind", return_value="linux"),
                mock.patch.object(server_editor_host, "is_wsl", return_value=False),
            ):
                self.assertEqual(unity_binary.resolve(), server_editor_host.normalize_unity_installation_path(editor_root))
                self.assertEqual("6000.3.2f1", server_editor_host.resolve_unity_app_version(editor_root))

    def test_normalize_unity_installation_path_supports_windows_editor_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            editor_root = Path(tmp_dir) / "6000.3.2f1"
            unity_binary = editor_root / "Editor" / "Unity.exe"
            unity_binary.parent.mkdir(parents=True)
            unity_binary.write_text("", encoding="utf-8")

            with (
                mock.patch.object(server_editor_host, "host_platform_kind", return_value="windows"),
                mock.patch.object(server_editor_host, "is_wsl", return_value=False),
            ):
                self.assertEqual(unity_binary.resolve(), server_editor_host.normalize_unity_installation_path(editor_root))
                self.assertEqual("6000.3.2f1", server_editor_host.resolve_unity_app_version(editor_root))

    def test_candidate_unity_editor_roots_are_platform_specific(self) -> None:
        with (
            mock.patch.object(server_editor_host, "configured_unity_editor_roots", return_value=[]),
            mock.patch.object(server_editor_host, "host_platform_kind", return_value="macos"),
        ):
            self.assertEqual([Path("/Applications/Unity/Hub/Editor")], server_editor_host.candidate_unity_editor_roots())

        with (
            mock.patch.object(server_editor_host, "configured_unity_editor_roots", return_value=[]),
            mock.patch.object(server_editor_host, "host_platform_kind", return_value="linux"),
            mock.patch.object(server_editor_host, "is_wsl", return_value=False),
        ):
            self.assertEqual(
                [Path.home() / "Unity" / "Hub" / "Editor", Path("/opt/Unity/Hub/Editor"), Path("/opt/unity/Hub/Editor")],
                server_editor_host.candidate_unity_editor_roots(),
            )

    def test_windows_editor_roots_env_matches_hub_editors_root_directly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            unity_exe = root / "6000.3.2f1" / "Editor" / "Unity.exe"
            unity_exe.parent.mkdir(parents=True)
            unity_exe.write_text("", encoding="utf-8")

            with (
                mock.patch.object(server_editor_host, "candidate_unity_editor_roots", return_value=[root]),
                mock.patch.object(server_editor_host, "host_platform_kind", return_value="windows"),
                mock.patch.object(server_editor_host, "is_wsl", return_value=False),
            ):
                discovered = server_editor_host.discover_unity_installations()

        self.assertEqual(["6000.3.2f1"], [version for version, _ in discovered])

    def test_windows_editor_roots_env_matches_single_version_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            version_dir = Path(tmp_dir) / "6000.3.2f1"
            unity_exe = version_dir / "Editor" / "Unity.exe"
            unity_exe.parent.mkdir(parents=True)
            unity_exe.write_text("", encoding="utf-8")

            with (
                mock.patch.object(server_editor_host, "candidate_unity_editor_roots", return_value=[version_dir]),
                mock.patch.object(server_editor_host, "host_platform_kind", return_value="windows"),
                mock.patch.object(server_editor_host, "is_wsl", return_value=False),
            ):
                discovered = server_editor_host.discover_unity_installations()

        self.assertEqual(["6000.3.2f1"], [version for version, _ in discovered])

    def test_unity_hub_secondary_install_root_joins_windows_candidate_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            appdata = Path(tmp_dir) / "Roaming"
            hub_dir = appdata / "UnityHub"
            hub_dir.mkdir(parents=True)
            (hub_dir / "secondaryInstallPath.json").write_text(
                json.dumps(str(Path(tmp_dir) / "UnityEditors")), encoding="utf-8"
            )
            program_files = Path(tmp_dir) / "Program Files"
            program_files.mkdir()

            env = {
                "APPDATA": str(appdata),
                "ProgramFiles": str(program_files),
                "ProgramW6432": str(program_files),
                "ProgramFiles(x86)": str(program_files),
            }
            with (
                mock.patch.dict(os.environ, env),
                mock.patch.object(server_editor_host, "configured_unity_editor_roots", return_value=[]),
                mock.patch.object(server_editor_host, "host_platform_kind", return_value="windows"),
                mock.patch.object(server_editor_host, "is_wsl", return_value=False),
            ):
                roots = server_editor_host.candidate_unity_editor_roots()

        self.assertIn(Path(tmp_dir) / "UnityEditors", roots)

    def test_unity_hub_secondary_install_root_absent_or_empty_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            appdata = Path(tmp_dir) / "Roaming"
            hub_dir = appdata / "UnityHub"
            hub_dir.mkdir(parents=True)

            with mock.patch.dict(os.environ, {"APPDATA": str(appdata)}):
                self.assertIsNone(server_editor_host.unity_hub_secondary_install_root())

            (hub_dir / "secondaryInstallPath.json").write_text('""', encoding="utf-8")
            with mock.patch.dict(os.environ, {"APPDATA": str(appdata)}):
                self.assertIsNone(server_editor_host.unity_hub_secondary_install_root())

    def test_unity_app_not_found_error_reports_searched_roots(self) -> None:
        searched = [Path("/definitely/missing/roots")]
        expected_root = str(searched[0])
        with (
            mock.patch.object(server_editor_host, "discover_unity_installations", return_value=[]),
            mock.patch.object(server_editor_host, "candidate_unity_editor_roots", return_value=searched),
        ):
            with self.assertRaises(server_core.ToolInvocationError) as raised:
                server_editor_host.detect_unity_app_path(None)

        self.assertEqual([expected_root], raised.exception.details.get("searched_roots"))
        self.assertIn(expected_root, raised.exception.message)

    @staticmethod
    def make_project_with_version(root: Path, version: str) -> Path:
        (root / "ProjectSettings").mkdir(parents=True)
        (root / "ProjectSettings" / "ProjectVersion.txt").write_text(
            f"m_EditorVersion: {version}\n", encoding="utf-8"
        )
        return root

    def test_unity_version_mismatch_fails_fast_instead_of_newest_fallback(self) -> None:
        installed = [
            ("2022.3.10f1", Path("/apps/2022.3.10f1/Unity")),
            ("6000.3.2f1", Path("/apps/6000.3.2f1/Unity")),
        ]
        searched = [Path("/apps")]
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = self.make_project_with_version(Path(tmp_dir) / "Project", "2021.3.58f1")
            with (
                mock.patch.object(server_editor_host, "discover_unity_installations", return_value=installed),
                mock.patch.object(server_editor_host, "candidate_unity_editor_roots", return_value=searched),
            ):
                with self.assertRaises(server_core.ToolInvocationError) as raised:
                    server_editor_host.detect_unity_app_path_for_project(project_root, None)

        self.assertEqual("unity_version_mismatch", raised.exception.code)
        self.assertEqual("2021.3.58f1", raised.exception.details.get("project_unity_version"))
        self.assertEqual(
            ["2022.3.10f1", "6000.3.2f1"], raised.exception.details.get("installed_versions")
        )
        self.assertEqual([str(searched[0])], raised.exception.details.get("searched_roots"))
        self.assertIn("2021.3.58f1", raised.exception.message)

    def test_matching_project_version_still_selects_that_install(self) -> None:
        matching_app = Path("/apps/2021.3.58f1/Unity")
        installed = [
            ("2021.3.58f1", matching_app),
            ("6000.3.2f1", Path("/apps/6000.3.2f1/Unity")),
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = self.make_project_with_version(Path(tmp_dir) / "Project", "2021.3.58f1")
            with mock.patch.object(
                server_editor_host, "discover_unity_installations", return_value=installed
            ):
                selected = server_editor_host.detect_unity_app_path_for_project(project_root, None)

        self.assertEqual(matching_app, selected)

    def test_missing_project_version_keeps_newest_install_fallback(self) -> None:
        newest_app = Path("/apps/6000.3.2f1/Unity")
        installed = [
            ("2022.3.10f1", Path("/apps/2022.3.10f1/Unity")),
            ("6000.3.2f1", newest_app),
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "Project"
            project_root.mkdir(parents=True)
            with mock.patch.object(
                server_editor_host, "discover_unity_installations", return_value=installed
            ):
                selected = server_editor_host.detect_unity_app_path_for_project(project_root, None)

        self.assertEqual(newest_app, selected)

    def test_version_known_but_zero_installs_reports_not_found_not_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = self.make_project_with_version(Path(tmp_dir) / "Project", "2021.3.58f1")
            with (
                mock.patch.object(server_editor_host, "discover_unity_installations", return_value=[]),
                mock.patch.object(
                    server_editor_host,
                    "candidate_unity_editor_roots",
                    return_value=[Path("/definitely/missing/roots")],
                ),
            ):
                with self.assertRaises(server_core.ToolInvocationError) as raised:
                    server_editor_host.detect_unity_app_path_for_project(project_root, None)

        self.assertEqual("unity_app_not_found", raised.exception.code)

    def test_discover_unity_installations_sorts_versions_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_unity = root / "2021.3.58f1" / "Editor" / "Unity"
            new_unity = root / "6000.3.2f1" / "Editor" / "Unity"
            for path in (old_unity, new_unity):
                path.parent.mkdir(parents=True)
                path.write_text("", encoding="utf-8")

            with (
                mock.patch.object(server_editor_host, "configured_unity_editor_roots", return_value=[]),
                mock.patch.object(server_editor_host, "candidate_unity_editor_roots", return_value=[root, root]),
                mock.patch.object(server_editor_host, "host_platform_kind", return_value="linux"),
                mock.patch.object(server_editor_host, "is_wsl", return_value=False),
            ):
                discovered = server_editor_host.discover_unity_installations()

        self.assertEqual(["2021.3.58f1", "6000.3.2f1"], [version for version, _ in discovered])
        self.assertEqual(2, len(discovered))

    def test_find_running_unity_editor_matches_windows_project_path_from_wsl(self) -> None:
        project_root = Path("/mnt/d/Development/Unity/_mtr/HumanFactory")
        command = (
            r'"D:\ProgramFiles\UnityHub\Editor\6000.3.2f1\Editor\Unity.exe" '
            r'-projectPath "D:\Development\Unity\_mtr\HumanFactory" -logFile foo.log'
        )

        with (
            mock.patch.object(server_editor_host, "is_wsl", return_value=True),
            mock.patch.object(server_editor_host, "list_process_commands", return_value=[(1234, command)]),
            mock.patch.object(server_editor_host, "pid_is_alive", return_value=True),
            mock.patch.object(server_editor_host, "resolve_unity_app_version", return_value="6000.3.2f1"),
        ):
            editors = server_editor_host.find_running_unity_editors_for_project(project_root)

        self.assertEqual([1234], [editor["pid"] for editor in editors])
        self.assertEqual(r"D:\Development\Unity\_mtr\HumanFactory", editors[0]["project_path"])

    def test_find_running_unity_editor_matches_macos_project_path(self) -> None:
        project_root = Path("/Users/dev/Project")
        command = (
            "/Applications/Unity/Hub/Editor/2022.3.60f1/Unity.app/Contents/MacOS/Unity "
            '-projectPath "/Users/dev/Project" -logFile /tmp/unity.log'
        )

        with (
            mock.patch.object(server_editor_host, "is_wsl", return_value=False),
            mock.patch.object(server_editor_host, "list_process_commands", return_value=[(2222, command)]),
            mock.patch.object(server_editor_host, "pid_is_alive", return_value=True),
            mock.patch.object(server_editor_host, "resolve_unity_app_version", return_value="2022.3.60f1"),
        ):
            editors = server_editor_host.find_running_unity_editors_for_project(project_root)

        self.assertEqual([2222], [editor["pid"] for editor in editors])
        self.assertEqual("/Users/dev/Project", editors[0]["project_path"])

    def test_find_running_unity_editor_matches_linux_project_path(self) -> None:
        project_root = Path("/home/dev/Project")
        command = "/opt/Unity/Hub/Editor/6000.3.2f1/Editor/Unity -projectPath /home/dev/Project -logFile /tmp/unity.log"

        with (
            mock.patch.object(server_editor_host, "is_wsl", return_value=False),
            mock.patch.object(server_editor_host, "list_process_commands", return_value=[(3333, command)]),
            mock.patch.object(server_editor_host, "pid_is_alive", return_value=True),
            mock.patch.object(server_editor_host, "resolve_unity_app_version", return_value="6000.3.2f1"),
        ):
            editors = server_editor_host.find_running_unity_editors_for_project(project_root)

        self.assertEqual([3333], [editor["pid"] for editor in editors])
        self.assertEqual("/home/dev/Project", editors[0]["project_path"])

    @unittest.skipIf(os.name == "nt", "simulates a POSIX host; native Windows takes the nt branch first")
    def test_pid_is_alive_uses_windows_tasklist_after_wsl_os_kill_systemerror(self) -> None:
        completed = mock.Mock(stdout="Unity.exe                  4321 Console\n", returncode=0)
        adapter = server_host_platform.HostPlatformAdapter(platform_kind="linux")

        with (
            mock.patch.object(server_host_platform, "is_wsl", return_value=True),
            mock.patch.object(server_host_platform.os, "kill", side_effect=SystemError("WinError 87")),
            mock.patch.object(server_host_platform.subprocess, "run", return_value=completed),
        ):
            self.assertTrue(adapter.pid_is_alive(4321))
            self.assertFalse(adapter.pid_is_alive(432))

    @unittest.skipIf(os.name == "nt", "simulates a POSIX host; native Windows takes the nt branch first")
    def test_pid_is_alive_detects_wsl_linux_interop_process(self) -> None:
        adapter = server_host_platform.HostPlatformAdapter(platform_kind="linux")

        with tempfile.TemporaryDirectory() as tmp_dir:
            proc_root = Path(tmp_dir)
            cmdline_path = proc_root / "4321" / "cmdline"
            cmdline_path.parent.mkdir(parents=True)
            cmdline_path.write_bytes(b"/mnt/c/Unity/Editor/Unity.exe\x00-projectPath\x00/mnt/d/Project")

            with (
                mock.patch.object(server_host_platform, "is_wsl", return_value=True),
                mock.patch.object(server_host_platform, "WSL_PROC_ROOT", proc_root),
                mock.patch.object(server_host_platform.os, "name", "nt"),
                mock.patch.object(sys, "platform", "win32"),
                mock.patch.object(server_host_platform.os, "readlink", return_value="/init"),
                mock.patch.object(server_host_platform.subprocess, "run") as mock_run,
            ):
                self.assertTrue(adapter.pid_is_alive(4321))
                mock_run.assert_not_called()

    def test_pid_is_alive_rejects_non_unity_wsl_linux_process_without_tasklist_fallback(self) -> None:
        adapter = server_host_platform.HostPlatformAdapter(platform_kind="linux")

        with tempfile.TemporaryDirectory() as tmp_dir:
            proc_root = Path(tmp_dir)
            cmdline_path = proc_root / "4321" / "cmdline"
            cmdline_path.parent.mkdir(parents=True)
            cmdline_path.write_bytes(b"/mnt/c/Windows/notepad.exe")

            with (
                mock.patch.object(server_host_platform, "is_wsl", return_value=True),
                mock.patch.object(server_host_platform, "WSL_PROC_ROOT", proc_root),
                mock.patch.object(server_host_platform.os, "readlink", return_value="/init"),
                mock.patch.object(server_host_platform.subprocess, "run") as mock_run,
            ):
                self.assertFalse(adapter.pid_is_alive(4321))
                mock_run.assert_not_called()

    def test_linux_process_listing_parses_ps_output(self) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout="  123 /opt/Unity/Editor/Unity -projectPath /home/dev/Project\nnot-a-pid bad\n  456 python server.py\n",
            stderr="",
        )
        adapter = server_host_platform.HostPlatformAdapter(platform_kind="linux")

        with (
            mock.patch.object(server_host_platform.os, "name", "posix"),
            mock.patch.object(server_host_platform, "is_wsl", return_value=False),
            mock.patch.object(server_host_platform.subprocess, "run", return_value=completed),
        ):
            report = adapter.list_process_commands_report()

        self.assertTrue(report["available"])
        self.assertEqual(
            [(123, "/opt/Unity/Editor/Unity -projectPath /home/dev/Project"), (456, "python server.py")],
            report["commands"],
        )

    def test_windows_process_listing_parses_powershell_json_object_and_array(self) -> None:
        adapter = server_host_platform.HostPlatformAdapter(platform_kind="windows")
        json_object = json.dumps({"ProcessId": 123, "CommandLine": r"C:\Unity.exe -projectPath C:\Project"})
        json_array = json.dumps(
            [
                {"ProcessId": 123, "CommandLine": r"C:\Unity.exe -projectPath C:\Project"},
                {"ProcessId": 456, "CommandLine": "python server.py"},
            ]
        )

        for stdout, expected in (
            (json_object, [(123, r"C:\Unity.exe -projectPath C:\Project")]),
            (json_array, [(123, r"C:\Unity.exe -projectPath C:\Project"), (456, "python server.py")]),
        ):
            with self.subTest(stdout=stdout):
                completed = mock.Mock(returncode=0, stdout=stdout, stderr="")
                with (
                    mock.patch.object(server_host_platform.os, "name", "nt"),
                    mock.patch.object(server_host_platform, "is_wsl", return_value=False),
                    mock.patch.object(server_host_platform.shutil, "which", return_value="powershell"),
                    mock.patch.object(server_host_platform.subprocess, "run", return_value=completed),
                ):
                    report = adapter.list_process_commands_report()

                self.assertTrue(report["available"])
                self.assertEqual(expected, report["commands"])

    def test_wsl_process_listing_missing_powershell_mentions_append_windows_path(self) -> None:
        adapter = server_host_platform.HostPlatformAdapter(platform_kind="linux")

        with (
            mock.patch.object(server_host_platform.os, "name", "posix"),
            mock.patch.object(server_host_platform, "is_wsl", return_value=True),
            mock.patch.object(server_host_platform.shutil, "which", return_value=None),
        ):
            report = adapter.list_process_commands_report()

        self.assertFalse(report["available"])
        self.assertEqual("process_listing_tool_missing", report["error_code"])
        self.assertIn("appendWindowsPath = true", report["stderr"])

    def test_batch_validation_command_converts_project_and_result_paths_under_wsl(self) -> None:
        with (
            mock.patch.object(server_editor_host, "resolve_unity_executable", return_value=Path("/mnt/d/Unity.exe")),
            mock.patch.object(server_editor_host, "is_wsl", return_value=True),
            mock.patch.object(server_editor_host, "wsl_to_windows_path", side_effect=lambda value: "WIN:" + str(value).replace('\\', '/')),
        ):
            command = server_editor_host.build_batch_validation_command(
                project_root=Path("/mnt/d/Project"),
                unity_app=Path("/mnt/d/Unity.exe"),
                log_path=Path("/mnt/d/Project/Library/XUUnityLightMcp/logs/batch.log"),
                result_path=Path("/mnt/d/Project/Library/XUUnityLightMcp/results/editmode.json"),
                action="editmode-tests",
            )

        self.assertIn("WIN:/mnt/d/Project", command)
        self.assertIn("WIN:/mnt/d/Project/Library/XUUnityLightMcp/logs/batch.log", command)
        self.assertIn("WIN:/mnt/d/Project/Library/XUUnityLightMcp/results/editmode.json", command)
        self.assertIn("-accept-apiupdate", command)

    def test_read_json_on_invalid_utf8_raises_json_decode_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_json = Path(tmp_dir) / "bad.json"
            bad_json.write_text("{ \"missing_comma\": 123 ", encoding="utf-8")

            with self.assertRaises(json.JSONDecodeError):
                server_core.read_json(bad_json)

    def test_discover_unity_installations_uses_case_insensitive_deduplication_under_wsl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path_a = root / "UnityHub" / "Editor" / "6000.3.2f1" / "Editor" / "Unity"
            path_b = root / "UnityHub" / "Editor" / "6000.3.2F1" / "Editor" / "Unity"

            for path in (path_a, path_b):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")

            with (
                mock.patch.object(server_editor_host, "configured_unity_editor_roots", return_value=[]),
                mock.patch.object(server_editor_host, "candidate_unity_editor_roots", return_value=[root]),
                mock.patch.object(server_editor_host, "host_platform_kind", return_value="linux"),
                mock.patch.object(server_editor_host, "is_wsl", return_value=True),
            ):
                discovered = server_editor_host.discover_unity_installations()

            self.assertEqual(1, len(discovered))

    def test_cmd_batch_build_player_converts_output_path_under_wsl(self) -> None:
        import server_cli_commands
        args = mock.Mock(
            project_root="/mnt/d/Project",
            unity_app="/mnt/d/Unity.exe",
            build_target="Android",
            output_path="/mnt/d/Project/Builds/Android.apk",
            scene_path=[],
            build_option=[],
            batch_log_path=None,
            result_file=None,
            dry_run=False,
            timeout_ms=1000,
            artifact_probe_file=None,
            artifact_probe_json=None,
            artifact_probe_warn_only=False,
            workspace_root=None,
            side_effect_mode="off",
            side_effect_allow_file=None,
            progress_interval_seconds=5,
            no_progress_stdout=True,
            batch_fallback_mode="auto",
            refresh_license=False,
        )

        with (
            mock.patch.object(server_cli_commands, "ensure_project_root", return_value=Path("/mnt/d/Project")),
            mock.patch.object(server_cli_commands, "detect_unity_app_path_for_project", return_value=Path("/mnt/d/Unity.exe")),
            mock.patch.object(
                server_cli_commands,
                "default_batch_build_result_path",
                return_value=Path("/mnt/d/Project/Library/XUUnityLightMcp/results/build_Android.json"),
            ),
            mock.patch.object(server_cli_commands, "resolve_batch_build_output_path", return_value="/mnt/d/Project/Builds/Android.apk"),
            mock.patch("server_host_platform.is_wsl", return_value=True),
            mock.patch("server_host_platform.wsl_to_windows_path", side_effect=lambda value: "WIN:" + str(value).replace('\\', '/')),
            mock.patch.object(server_cli_commands, "build_plain_batch_build_command", return_value=["Unity.exe"]) as mock_build_cmd,
            mock.patch.object(server_cli_commands, "run_batch_operation") as mock_run_batch,
        ):
            server_cli_commands.cmd_batch_build_player(args)

            mock_build_cmd.assert_called_once()
            self.assertEqual("WIN:/mnt/d/Project/Builds/Android.apk", mock_build_cmd.call_args[1].get("output_path"))

            mock_run_batch.assert_called_once()
            gui_args = mock_run_batch.call_args[1].get("gui_operation_args")
            self.assertEqual("WIN:/mnt/d/Project/Builds/Android.apk", gui_args.get("outputPath"))
            self.assertEqual("WIN:/mnt/d/Project/Library/XUUnityLightMcp/results/build_Android.json", gui_args.get("resultFile"))

    @unittest.skipIf(os.name == "nt", "simulates a POSIX host; native Windows takes the nt branch first")
    def test_pid_is_alive_bypasses_os_kill_under_wsl(self) -> None:
        completed = mock.Mock(stdout="Unity.exe                  4321 Console\n", returncode=0)
        adapter = server_host_platform.HostPlatformAdapter(platform_kind="linux")

        mock_kill = mock.Mock()
        with (
            mock.patch.object(server_host_platform, "is_wsl", return_value=True),
            mock.patch.object(server_host_platform.os, "kill", mock_kill),
            mock.patch.object(server_host_platform.subprocess, "run", return_value=completed),
        ):
            self.assertTrue(adapter.pid_is_alive(4321))
            mock_kill.assert_not_called()

    @unittest.skipIf(os.name == "nt", "simulates a POSIX host; native Windows takes the nt branch first")
    def test_terminate_editor_pid_kills_wsl_linux_interop_process(self) -> None:
        with (
            mock.patch.object(server_editor_host, "is_wsl", return_value=True),
            mock.patch.object(server_editor_host, "pid_is_alive", side_effect=[True, False]) as mock_alive,
            mock.patch.object(server_editor_host, "wsl_linux_unity_interop_pid_status", return_value=True),
            mock.patch.object(server_editor_host.os, "kill") as mock_kill,
            mock.patch.object(server_editor_host.subprocess, "run") as mock_run,
        ):
            self.assertTrue(server_editor_host.terminate_editor_pid(4321, 1000))

        mock_alive.assert_called()
        mock_kill.assert_called_once_with(4321, server_editor_host.signal.SIGTERM)
        mock_run.assert_not_called()

    @unittest.skipIf(os.name == "nt", "simulates WSL from a POSIX test host")
    def test_terminate_editor_pid_uses_single_pid_taskkill_for_wsl_windows_process(self) -> None:
        completed = mock.Mock(returncode=0)
        with (
            mock.patch.object(server_editor_host, "is_wsl", return_value=True),
            mock.patch.object(server_editor_host, "pid_is_alive", side_effect=[True, False]),
            mock.patch.object(
                server_editor_host, "wsl_linux_unity_interop_pid_status", return_value=False
            ),
            mock.patch.object(
                server_editor_host.subprocess, "run", return_value=completed
            ) as mock_run,
        ):
            self.assertTrue(server_editor_host.terminate_editor_pid(4321, 1000))

        argv = mock_run.call_args.args[0]
        self.assertIn(argv[0], {"taskkill.exe", "taskkill"})
        self.assertEqual(["/F", "/PID", "4321"], argv[1:])
        self.assertNotIn("/T", argv)

    def test_process_visibility_warns_on_missing_wslpath_under_wsl(self) -> None:
        with (
            mock.patch.object(
                server_editor_host,
                "list_process_commands_report",
                return_value={
                    "available": True,
                    "commands": [],
                    "error_code": "",
                    "stderr": "",
                    "platform_kind": "linux",
                },
            ),
            mock.patch.object(server_editor_host, "is_wsl", return_value=True),
            mock.patch.object(server_host_platform, "is_wsl", return_value=True),
            mock.patch.object(server_host_platform.shutil, "which", return_value=None),
        ):
            summary = server_editor_host.process_visibility_summary()

        self.assertFalse(summary["process_visibility_wslpath_available"])
        self.assertIn("wslpath_missing", " ".join(summary["process_visibility_warnings"]))

    def test_read_json_raises_wrapped_json_decode_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_json = Path(tmp_dir) / "bad.json"
            bad_json.write_text("{ missing_quotes: 123 }", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError) as context:
                server_core.read_json(bad_json)
            self.assertIn("Failed to parse JSON in", str(context.exception))
            self.assertIn("bad.json", str(context.exception))

    def test_read_json_raises_wrapped_unicode_decode_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_json = Path(tmp_dir) / "bad.json"
            bad_json.write_bytes(b"\xff\xff\xff\xff\x00\x00\xff")
            with self.assertRaises(UnicodeDecodeError) as context:
                server_core.read_json(bad_json)
            self.assertIn("Failed to decode text in", str(context.exception))
            self.assertIn("bad.json", str(context.exception))

    @unittest.skipIf(os.name == "nt", "simulates a POSIX host; native Windows takes the nt branch first")
    def test_pid_is_alive_falls_back_on_local_linux_process_collision(self) -> None:
        completed = mock.Mock(stdout="Unity.exe                  4321 Console\n", returncode=0)
        adapter = server_host_platform.HostPlatformAdapter(platform_kind="linux")

        with (
            mock.patch.object(server_host_platform, "is_wsl", return_value=True),
            mock.patch.object(server_host_platform.os, "readlink", return_value="/usr/bin/python3"),
            mock.patch.object(server_host_platform.subprocess, "run", return_value=completed) as mock_run,
        ):
            self.assertTrue(adapter.pid_is_alive(4321))
            mock_run.assert_called_once()
            self.assertEqual("tasklist.exe", mock_run.call_args[0][0][0])

    def test_cmd_batch_compile_matrix_converts_config_file_under_wsl(self) -> None:
        import server_cli_commands
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            project_root = tmp_path / "Project"
            project_root.mkdir()
            config_file = project_root / "matrix.json"
            config_file.write_text("{}", encoding="utf-8")

            args = mock.Mock(
                project_root=str(project_root),
                unity_app="/mnt/d/Unity.exe",
                config_file=str(config_file),
                batch_log_path=None,
                result_file=None,
                dry_run=False,
                timeout_ms=1000,
                workspace_root=None,
                side_effect_mode="off",
                side_effect_allow_file=None,
                progress_interval_seconds=5,
                no_progress_stdout=True,
                batch_fallback_mode="auto",
                refresh_license=False,
            )

            with (
                mock.patch.object(server_cli_commands, "ensure_project_root", return_value=project_root),
                mock.patch.object(server_cli_commands, "detect_unity_app_path_for_project", return_value=Path("/mnt/d/Unity.exe")),
                mock.patch.object(server_cli_commands, "load_json_file", return_value={}),
                mock.patch("server_host_platform.is_wsl", return_value=True),
                mock.patch("server_host_platform.wsl_to_windows_path", side_effect=lambda value: "WIN:" + str(value).replace('\\', '/')),
                mock.patch.object(server_cli_commands, "build_batch_validation_command", return_value=["Unity.exe"]) as mock_build_cmd,
                mock.patch.object(server_cli_commands, "run_batch_operation") as mock_run_batch,
            ):
                server_cli_commands.cmd_batch_compile_matrix(args)

                mock_build_cmd.assert_called_once()
                extra_args = mock_build_cmd.call_args[1].get("extra_args")
                self.assertIn("WIN:" + str(config_file.resolve()).replace('\\', '/'), extra_args)

    def test_cmd_batch_build_config_compile_matrix_uses_project_temp_dir_and_converts_path_under_wsl(self) -> None:
        import server_cli_commands
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            project_root = tmp_path / "Project"
            project_root.mkdir()

            args = mock.Mock(
                project_root=str(project_root),
                unity_app="/mnt/d/Unity.exe",
                build_config_asset="Assets/Config.asset",
                profile=[],
                target=[],
                stop_on_first_failure=False,
                batch_log_path=None,
                result_file=None,
                dry_run=False,
                timeout_ms=1000,
                workspace_root=None,
                side_effect_mode="off",
                side_effect_allow_file=None,
                progress_interval_seconds=5,
                no_progress_stdout=True,
                batch_fallback_mode="auto",
                refresh_license=False,
            )

            fake_plan = {"assetPath": "Assets/Config.asset", "profiles": [], "matrixArgs": {}}

            with (
                mock.patch.object(server_cli_commands, "ensure_project_root", return_value=project_root),
                mock.patch.object(server_cli_commands, "detect_unity_app_path_for_project", return_value=Path("/mnt/d/Unity.exe")),
                mock.patch.object(server_cli_commands, "build_compile_matrix_args_from_build_config", return_value=fake_plan),
                mock.patch("server_host_platform.is_wsl", return_value=True),
                mock.patch("server_host_platform.wsl_to_windows_path", side_effect=lambda value: "WIN:" + str(value).replace('\\', '/')),
                mock.patch.object(server_cli_commands, "build_batch_validation_command", return_value=["Unity.exe"]) as mock_build_cmd,
                mock.patch.object(server_cli_commands, "run_batch_operation") as mock_run_batch,
            ):
                server_cli_commands.cmd_batch_build_config_compile_matrix(args)

                mock_build_cmd.assert_called_once()
                extra_args = mock_build_cmd.call_args[1].get("extra_args")
                self.assertTrue(any(
                    str(arg).startswith("WIN:") and
                    "Library/XUUnityLightMcp/temp" in str(arg).replace('\\', '/') and
                    str(arg).endswith("_xuunity_compile_matrix.json")
                    for arg in extra_args
                ))

    @unittest.skipIf(os.name == "nt", "simulates a POSIX host; native Windows takes the nt branch first")
    def test_pid_is_alive_handles_cygwin_msys_platform_routing(self) -> None:
        completed = mock.Mock(stdout="Unity.exe                  1234 Console\n", returncode=0)
        adapter = server_host_platform.HostPlatformAdapter(platform_kind="linux")
        
        with (
            mock.patch.object(sys, "platform", "msys"),
            mock.patch.object(server_host_platform, "is_wsl", return_value=False),
            mock.patch.object(server_host_platform.subprocess, "run", return_value=completed) as mock_run,
        ):
            self.assertTrue(adapter.pid_is_alive(1234))
            mock_run.assert_called_once()
            self.assertIn("tasklist", mock_run.call_args[0][0])

    def test_terminate_editor_pid_handles_cygwin_msys_platform_routing(self) -> None:
        completed = mock.Mock(returncode=0)
        with (
            mock.patch.object(sys, "platform", "cygwin"),
            mock.patch.object(server_editor_host, "is_wsl", return_value=False),
            mock.patch.object(server_editor_host, "pid_is_alive", side_effect=[True, False]),
            mock.patch.object(server_editor_host.subprocess, "run", return_value=completed) as mock_run,
        ):
            self.assertTrue(server_editor_host.terminate_editor_pid(1234, 1000))
            mock_run.assert_called_once()
            self.assertIn("taskkill", mock_run.call_args[0][0])
            self.assertNotIn("/T", mock_run.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
