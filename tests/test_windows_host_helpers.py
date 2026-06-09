import json
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

    def test_batch_validation_command_converts_project_and_result_paths_under_wsl(self) -> None:
        with (
            mock.patch.object(server_editor_host, "resolve_unity_executable", return_value=Path("/mnt/d/Unity.exe")),
            mock.patch.object(server_editor_host, "is_wsl", return_value=True),
            mock.patch.object(server_editor_host, "wsl_to_windows_path", side_effect=lambda value: f"WIN:{value}"),
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


if __name__ == "__main__":
    unittest.main()
