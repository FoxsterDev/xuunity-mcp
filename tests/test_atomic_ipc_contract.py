"""Atomic IPC publication contract.

Guards the Windows torn-read/torn-write walls:
- Python `write_json` publishes via temp + os.replace so the editor request
  pump never parses a half-written inbox request;
- the file-IPC response reader retries a mid-write/locked response until the
  deadline instead of consuming (unlinking) a half-written file;
- every C# IPC file the Python host polls goes through
  XUUnityLightMcpAtomicFileWriter (temp + File.Replace).
"""

import json
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
if str(TEMPLATES_DIR) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_DIR))

import server_bridge_final_status
import server_bridge_transport
from server_bridge_paths import bridge_state_path, inbox_dir, outbox_dir, response_path
from server_core import ToolInvocationError, write_json

REPO_ROOT = Path(__file__).resolve().parents[1]
CSHARP_EDITOR_ROOT = REPO_ROOT / "packages" / "com.xuunity.light-mcp" / "Editor"
ATOMIC_WRITER_NAME = "XUUnityLightMcpAtomicFileWriter.cs"
FIXED_REQUEST_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def make_bridge_project(root: Path) -> Path:
    inbox_dir(root).mkdir(parents=True, exist_ok=True)
    outbox_dir(root).mkdir(parents=True, exist_ok=True)
    state_path = bridge_state_path(root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "editor_pid": 0,
                "bridge_generation": 1,
                "bridge_session_id": "session-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return root


class WriteJsonAtomicityTest(unittest.TestCase):
    def test_writes_payload_and_leaves_no_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "nested" / "state.json"
            write_json(target, {"value": "данные"})

            self.assertEqual({"value": "данные"}, json.loads(target.read_text(encoding="utf-8")))
            self.assertTrue(target.read_text(encoding="utf-8").endswith("\n"))
            self.assertEqual([], list(target.parent.glob("*.tmp")))

    def test_publishes_via_replace_of_non_json_temp_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "request.json"
            observed: list[tuple[str, str]] = []

            import os as os_module

            original = os_module.replace

            def recording_replace(src, dst):
                observed.append((str(src), str(dst)))
                return original(src, dst)

            with mock.patch.object(os_module, "replace", side_effect=recording_replace):
                write_json(target, {"ok": True})

            self.assertEqual(1, len(observed))
            src, dst = observed[0]
            self.assertEqual(str(target), dst)
            self.assertTrue(src.endswith(".tmp"), src)
            self.assertEqual(str(target.parent), str(Path(src).parent))
            self.assertFalse(
                src.endswith(".json"),
                "temp name must not match the *.json glob the editor pump scans",
            )

    def test_retries_replace_on_permission_error_then_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "state.json"

            import os as os_module

            original = os_module.replace
            attempts: list[int] = []

            def flaky_replace(src, dst):
                attempts.append(1)
                if len(attempts) < 3:
                    raise PermissionError("destination briefly held by a reader")
                return original(src, dst)

            with mock.patch.object(os_module, "replace", side_effect=flaky_replace):
                write_json(target, {"attempt": "retried"})

            self.assertEqual(3, len(attempts))
            self.assertEqual({"attempt": "retried"}, json.loads(target.read_text(encoding="utf-8")))
            self.assertEqual([], list(target.parent.glob("*.tmp")))

    def test_falls_back_to_direct_write_when_replace_stays_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "state.json"

            import os as os_module

            with mock.patch.object(
                os_module, "replace", side_effect=PermissionError("held open")
            ):
                write_json(target, {"fallback": True})

            self.assertEqual({"fallback": True}, json.loads(target.read_text(encoding="utf-8")))
            self.assertEqual([], list(target.parent.glob("*.tmp")))


class FileIpcResponseReaderTest(unittest.TestCase):
    def invoke(self, project_root: Path, timeout_ms: int):
        transport = server_bridge_transport.FileIpcBridgeTransport()
        with mock.patch.object(
            server_bridge_transport.uuid, "uuid4", return_value=FIXED_REQUEST_ID
        ):
            return transport.invoke(project_root, "unity.status", {}, timeout_ms)

    def outbox_response_path(self, project_root: Path) -> Path:
        return response_path(project_root, str(FIXED_REQUEST_ID))

    def test_partial_response_is_not_consumed_and_times_out(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_bridge_project(Path(tmp_dir) / "Proj")
            response_path = self.outbox_response_path(project_root)
            response_path.write_text('{"status": "ok", "payload_json": "{', encoding="utf-8")

            with self.assertRaises(ToolInvocationError) as ctx:
                self.invoke(project_root, timeout_ms=700)

            self.assertEqual("operation_timeout", ctx.exception.code)
            self.assertTrue(
                response_path.is_file(),
                "half-written response must stay on disk for the next poll",
            )

    def test_valid_response_is_returned_and_consumed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_bridge_project(Path(tmp_dir) / "Proj")
            response_path = self.outbox_response_path(project_root)
            response_path.write_text(
                json.dumps({"status": "ok", "payload_type": "unity.status", "payload_json": "{}"}),
                encoding="utf-8",
            )

            response, request_id, _ = self.invoke(project_root, timeout_ms=5000)

            self.assertEqual("ok", response["status"])
            self.assertEqual(str(FIXED_REQUEST_ID), request_id)
            self.assertFalse(response_path.is_file())

    def test_response_completed_mid_flight_is_picked_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_bridge_project(Path(tmp_dir) / "Proj")
            response_path = self.outbox_response_path(project_root)
            response_path.write_text('{"status": "ok"', encoding="utf-8")

            def finish_write() -> None:
                time.sleep(0.4)
                response_path.write_text(
                    json.dumps({"status": "ok", "payload_type": "unity.status", "payload_json": "{}"}),
                    encoding="utf-8",
                )

            writer = threading.Thread(target=finish_write)
            writer.start()
            try:
                response, _, _ = self.invoke(project_root, timeout_ms=5000)
            finally:
                writer.join()

            self.assertEqual("ok", response["status"])
            self.assertFalse(response_path.is_file())

    def test_recovered_response_read_failure_leaves_file_for_next_poll(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = make_bridge_project(Path(tmp_dir) / "Proj")
            request_id = str(FIXED_REQUEST_ID)
            path = server_bridge_final_status.response_path(project_root, request_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"status": "ok', encoding="utf-8")

            recovered = server_bridge_final_status.try_take_recovered_response(
                project_root, request_id
            )

            self.assertIsNone(recovered)
            self.assertTrue(path.is_file())

            path.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
            recovered = server_bridge_final_status.try_take_recovered_response(
                project_root, request_id
            )
            self.assertEqual({"status": "ok"}, recovered)
            self.assertFalse(path.is_file())


class CSharpAtomicWriterContractTest(unittest.TestCase):
    def csharp_files(self) -> list[Path]:
        files = sorted(CSHARP_EDITOR_ROOT.rglob("*.cs"))
        self.assertTrue(files, f"no C# sources found under {CSHARP_EDITOR_ROOT}")
        return files

    def test_only_the_atomic_writer_calls_file_write_all_text(self) -> None:
        offenders = []
        for source in self.csharp_files():
            if source.name == ATOMIC_WRITER_NAME:
                continue
            if "File.WriteAllText(" in source.read_text(encoding="utf-8"):
                offenders.append(str(source.relative_to(REPO_ROOT)))
        self.assertEqual(
            [],
            offenders,
            "IPC files must be published through XUUnityLightMcpAtomicFileWriter",
        )

    def test_atomic_writer_publishes_via_temp_and_replace(self) -> None:
        writer = CSHARP_EDITOR_ROOT / "Core" / ATOMIC_WRITER_NAME
        text = writer.read_text(encoding="utf-8")
        self.assertIn('".tmp"', text)
        self.assertIn("File.Replace(", text)
        self.assertIn("File.Move(", text)
        self.assertNotIn(
            "Thread.Sleep",
            text,
            "writer runs on the editor main thread (heartbeat/pump); it must "
            "fall back to the legacy write instead of sleeping",
        )
        meta = writer.with_name(writer.name + ".meta")
        self.assertTrue(meta.is_file(), "new package source needs a committed .meta")

    def test_no_main_thread_sleeps_in_editor_package(self) -> None:
        # The bridge runs on EditorApplication.update; any Thread.Sleep there
        # is a frame stall. GameViewUtility's screenshot settling delay is the
        # single documented pre-existing exception (on-demand, not per-tick).
        allowed = {"XUUnityLightMcpGameViewUtility.cs"}
        offenders = []
        for source in self.csharp_files():
            if source.name in allowed:
                continue
            if "Thread.Sleep" in source.read_text(encoding="utf-8"):
                offenders.append(str(source.relative_to(REPO_ROOT)))
        self.assertEqual([], offenders)

    def test_bridge_state_and_response_writers_use_atomic_publisher(self) -> None:
        for relative in (
            Path("Bridge") / "XUUnityLightMcpBridgeStateWriter.cs",
            Path("Core") / "XUUnityLightMcpResponseWriter.cs",
        ):
            text = (CSHARP_EDITOR_ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("XUUnityLightMcpAtomicFileWriter.WriteAllText(", text, str(relative))

    def test_package_meta_guids_are_unique(self) -> None:
        guids: dict[str, str] = {}
        for meta in sorted((REPO_ROOT / "packages").rglob("*.meta")):
            for line in meta.read_text(encoding="utf-8").splitlines():
                if line.startswith("guid: "):
                    guid = line.split(":", 1)[1].strip()
                    self.assertNotIn(
                        guid,
                        guids,
                        f"duplicate guid in {meta} and {guids.get(guid)}",
                    )
                    guids[guid] = str(meta)
                    break


if __name__ == "__main__":
    unittest.main()
