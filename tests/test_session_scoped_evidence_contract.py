"""Evidence-surface contract from the 2026-08-03 multi-scene UI targeting retro.

Every case here encodes a way the previous evidence layer misled an operator:

- an unanchored `source=editor_log` grep matched a marker line written by a *previous* play session,
  so a shell wait loop returned immediately on a stale line;
- a live-editor batch refusal was counted as `projects_failed`, which reads as "the code does not compile";
- a compile refused during Play Mode reported a generic "editor is busy";
- a refresh that settled during Play Mode reported `post_settle_compile: passed` while asset import was deferred;
- `includeImage: true` returned a 184k-character payload whose only useful field was `file_path`;
- `unity_ui_*` resolved targets in the active scene only, and said `ui_target_not_found` when the object
  was merely out of scope.

The C# half of the UI-scope contract is asserted from source here because it needs a live editor to run.
"""

import json
import os
import tempfile
import time
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"
RUNNER_DIR = REPO_ROOT / "scripts" / "testing"
for candidate in (TEMPLATES_DIR, RUNNER_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_multi_project
import server_batch_orchestrator
import server_bridge_payloads
import server_bridge_journal
import server_bridge_paths
import server_core
import server_editor_host_paths  # noqa: E402
import server_health
import server_specs

PACKAGE_EDITOR_ROOT = REPO_ROOT / "packages" / "com.xuunity.light-mcp" / "Editor"


def write_log(path: Path, text: str, newline: str = "\n") -> bytes:
    """Write a log byte-exactly and return the bytes written.

    Path.write_text() applies platform newline translation, so on Windows every "\n" becomes "\r\n" and the
    file stops matching a byte offset the test computed from the source string. Anchors are byte offsets, so
    these tests must own the exact bytes. `newline` also lets a case assert the CRLF layout Unity writes on
    Windows rather than merely neutralising it.
    """

    data = text.replace("\n", newline).encode("utf-8")
    path.write_bytes(data)
    return data


def read_source(relative: str) -> str:
    return (PACKAGE_EDITOR_ROOT / relative).read_text(encoding="utf-8")


class EditorLogSinceAnchorTests(unittest.TestCase):
    """A `since` anchor must bound the search to the current session, not the whole accumulated log."""

    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.log = self.root / "Editor.log"
        self.stale = "hook fired MARKER\n" * 3
        self.fresh = "hook fired MARKER\n" * 2
        self.offset = len(write_log(self.log, self.stale))
        write_log(self.log, self.stale + self.fresh)
        self.bridge_state = {
            "editor_log_offset_at_playmode_start": self.offset,
            "editor_log_playmode_started_utc": "2026-08-03T10:00:00Z",
            "editor_log_offset_at_bridge_generation_start": self.offset,
            "editor_log_offset_bridge_generation": 7,
        }

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_unanchored_grep_still_matches_previous_session_lines(self) -> None:
        payload = server_health.grep_editor_log_payload(self.root, self.log, pattern="MARKER")

        self.assertEqual(5, payload["match_count"])
        self.assertEqual("editor_log_spans_multiple_sessions", payload["result_trust_class"])
        self.assertTrue(payload["stale_match_caveat"])
        self.assertFalse(payload["since_anchor_degraded"])

    def test_playmode_anchor_excludes_previous_session_lines(self) -> None:
        payload = server_health.grep_editor_log_payload(
            self.root,
            self.log,
            pattern="MARKER",
            since="playmode_start",
            bridge_state=self.bridge_state,
        )

        self.assertEqual(2, payload["match_count"])
        self.assertEqual("session_scoped_editor_log", payload["result_trust_class"])
        self.assertEqual("matched", payload["search_verdict"])
        self.assertEqual("", payload["stale_match_caveat"])
        self.assertEqual("playmode_start", payload["since_anchor"]["resolved"])
        self.assertEqual(self.offset, payload["since_anchor"]["start_offset_bytes"])

    def test_a_complete_anchored_zero_match_is_a_real_negative(self) -> None:
        payload = server_health.grep_editor_log_payload(
            self.root,
            self.log,
            pattern="ABSENT",
            since="playmode_start",
            bridge_state=self.bridge_state,
        )

        self.assertFalse(payload["scope_truncated"])
        self.assertEqual("not_matched", payload["search_verdict"])
        self.assertEqual("complete_anchored_scope_searched", payload["search_verdict_reason"])
        self.assertNotIn("recommended_next_action", payload)

    def test_anchored_line_numbers_stay_absolute_in_the_editor_log(self) -> None:
        payload = server_health.grep_editor_log_payload(
            self.root,
            self.log,
            pattern="MARKER",
            since="playmode_start",
            bridge_state=self.bridge_state,
        )

        self.assertEqual("editor_log_absolute", payload["line_numbering_basis"])
        self.assertEqual(4, payload["searched_from_line"])
        self.assertEqual([4, 5], [item["line"] for item in payload["items"]])

    def test_bridge_generation_anchor_echoes_the_generation_it_resolved(self) -> None:
        payload = server_health.grep_editor_log_payload(
            self.root,
            self.log,
            pattern="MARKER",
            since="bridge_generation",
            bridge_state=self.bridge_state,
        )

        self.assertTrue(payload["since_anchor"]["anchored"])
        self.assertEqual(7, payload["since_anchor"]["bridge_generation"])

    def test_a_requested_anchor_the_editor_never_recorded_is_reported_not_faked(self) -> None:
        payload = server_health.grep_editor_log_payload(
            self.root,
            self.log,
            pattern="MARKER",
            since="playmode_start",
            bridge_state={},
        )

        self.assertEqual("anchor_unavailable", payload["since_anchor"]["resolved"])
        self.assertTrue(payload["since_anchor_degraded"])
        self.assertTrue(payload["stale_match_caveat"])
        self.assertTrue(payload["since_anchor"]["recommended_next_action"])

    def test_a_rotated_log_smaller_than_the_offset_is_reported_as_stale(self) -> None:
        write_log(self.log, "short\n")

        anchor = server_health.resolve_editor_log_since_anchor(
            self.log,
            since="playmode_start",
            bridge_state=self.bridge_state,
        )

        self.assertEqual("anchor_stale", anchor["resolved"])
        self.assertFalse(anchor["anchored"])

    def test_unsupported_anchor_names_the_supported_set(self) -> None:
        anchor = server_health.resolve_editor_log_since_anchor(self.log, since="last_tuesday")

        self.assertEqual("unsupported_anchor", anchor["resolved"])
        self.assertEqual(list(server_health.SINCE_ANCHORS), anchor["supported_anchors"])

    def test_request_id_anchor_uses_the_offset_the_editor_journalled(self) -> None:
        """Per-request anchoring answers "did *this* call log it", which playmode_start cannot: one play session
        holds many operations. The offset comes from the request_started journal event, so it costs one stat per
        operator-issued request and never a stat inside the 0.5 s request pump."""

        payload = server_health.grep_editor_log_payload(
            self.root,
            self.log,
            pattern="MARKER",
            since="request_id",
            since_request_id="req-42",
            journal_events=[
                {"event_type": "request_submitted", "request_id": "req-42"},
                {
                    "event_type": "request_started",
                    "request_id": "req-42",
                    "editor_log_offset_bytes": self.offset,
                    "editor_log_path": str(self.log),
                },
                {"event_type": "request_completed", "request_id": "req-42"},
            ],
        )

        self.assertEqual(2, payload["match_count"])
        self.assertEqual("session_scoped_editor_log", payload["result_trust_class"])
        self.assertEqual("request_id", payload["since_anchor"]["resolved"])
        self.assertEqual("req-42", payload["since_anchor"]["since_request_id"])
        self.assertEqual(self.offset, payload["since_anchor"]["start_offset_bytes"])

    def test_request_id_anchor_without_a_request_id_says_so(self) -> None:
        anchor = server_health.resolve_editor_log_since_anchor(self.log, since="request_id")

        self.assertEqual("anchor_argument_missing", anchor["resolved"])
        self.assertFalse(anchor["anchored"])

    def test_a_journal_without_the_offset_degrades_instead_of_guessing(self) -> None:
        """Requests journalled by an older package carry no offset; that must not silently widen the search."""

        payload = server_health.grep_editor_log_payload(
            self.root,
            self.log,
            pattern="MARKER",
            since="request_id",
            since_request_id="req-old",
            journal_events=[{"event_type": "request_started", "request_id": "req-old"}],
        )

        self.assertEqual("anchor_unavailable", payload["since_anchor"]["resolved"])
        self.assertTrue(payload["since_anchor_degraded"])
        self.assertIn("journal", payload["since_anchor"]["anchor_unavailable_reason"])

    def test_the_editor_journals_the_offset_at_request_start_not_in_the_pump(self) -> None:
        package = REPO_ROOT / "packages" / "com.xuunity.light-mcp" / "Editor"
        journal = (package / "Bridge" / "XUUnityLightMcpRequestJournal.cs").read_text(encoding="utf-8")
        models = (package / "Core" / "XUUnityLightMcpBridgeModels.cs").read_text(encoding="utf-8")

        self.assertIn("public long editor_log_offset_bytes;", models)
        started = journal.index("WriteRequestStarted")
        completed = journal.index("WriteRequestCompleted")
        offset_call = journal.index("XUUnityLightMcpEditorLogAnchors.CurrentEditorLogLengthBytes()")
        self.assertTrue(started < offset_call < completed, "the offset must be stamped by WriteRequestStarted")
        self.assertEqual(
            1,
            journal.count("XUUnityLightMcpEditorLogAnchors.CurrentEditorLogLengthBytes()"),
            "one stat per started request; never a second call site",
        )

    def test_bridge_bootstrap_refuses_import_workers_and_journals_main_writer_identity(self) -> None:
        package = REPO_ROOT / "packages" / "com.xuunity.light-mcp" / "Editor"
        bootstrap = (package / "Bridge" / "XUUnityLightMcpBridgeBootstrap.cs").read_text(encoding="utf-8")
        journal = (package / "Bridge" / "XUUnityLightMcpRequestJournal.cs").read_text(encoding="utf-8")
        models = (package / "Core" / "XUUnityLightMcpBridgeModels.cs").read_text(encoding="utf-8")

        guard = bootstrap.index("processClass == XUUnityLightMcpBridgeProcessIdentity.ImportWorkerProcessClass")
        initialize = bootstrap.index("XUUnityLightMcpBridgeRuntimeState.InitializeBridgeSession()")
        self.assertLess(guard, initialize, "the import-worker refusal must run before any bridge state or transport setup")
        self.assertIn("AssetDatabase.IsAssetImportWorkerProcess()", bootstrap)
        self.assertIn('event_type = "bridge_bootstrap_attached"', journal)
        self.assertIn("editor_pid = process.Id", journal)
        self.assertIn("process_class = processClass", journal)
        self.assertIn("editor_log_path = XUUnityLightMcpEditorLogAnchors.CurrentEditorLogPath()", journal)
        self.assertIn("public string bridge_process_class = \"\";", models)
        self.assertIn("public bool runtime_execution_allowed;", models)

    def test_both_console_tools_accept_the_request_id_argument(self) -> None:
        for tool_name in ("unity_console_grep", "unity_console_tail"):
            with self.subTest(tool=tool_name):
                self.assertIn("sinceRequestId", server_specs.TOOLS[tool_name]["inputSchema"]["properties"])

    def test_an_offset_measured_against_a_different_log_is_refused(self) -> None:
        """The editor stamps offsets against Application.consoleLogPath; the host defaults to the project-local
        log. Those are the same file only when the host launched the editor with -logFile. An editor opened from
        the Hub writes to the platform Editor.log, and applying its offset to the project-local log would scope
        the search to an arbitrary byte while still reporting session_scoped_editor_log — the precise class of
        false trust this retro exists to remove."""

        payload = server_health.grep_editor_log_payload(
            self.root,
            self.log,
            pattern="MARKER",
            since="playmode_start",
            bridge_state={
                **self.bridge_state,
                "editor_log_path": "/somewhere/else/Library/Logs/Unity/Editor.log",
            },
        )

        self.assertEqual("anchor_log_mismatch", payload["since_anchor"]["resolved"])
        self.assertFalse(payload["since_anchor"]["anchored"])
        self.assertTrue(payload["since_anchor_degraded"])
        self.assertTrue(payload["stale_match_caveat"])
        self.assertEqual(5, payload["match_count"], "must fall back to the full tail, not a bogus scope")
        self.assertEqual("editor_log_spans_multiple_sessions", payload["result_trust_class"])
        self.assertIn("editorLogPath", payload["since_anchor"]["recommended_next_action"])

    def test_a_matching_log_path_still_anchors(self) -> None:
        payload = server_health.grep_editor_log_payload(
            self.root,
            self.log,
            pattern="MARKER",
            since="playmode_start",
            bridge_state={**self.bridge_state, "editor_log_path": str(self.log)},
        )

        self.assertEqual("playmode_start", payload["since_anchor"]["resolved"])
        self.assertEqual(2, payload["match_count"])

    def test_the_request_id_anchor_is_guarded_by_the_same_check(self) -> None:
        payload = server_health.grep_editor_log_payload(
            self.root,
            self.log,
            pattern="MARKER",
            since="request_id",
            since_request_id="req-42",
            bridge_state={"editor_log_path": "/somewhere/else/Editor.log"},
            journal_events=[
                {"event_type": "request_started", "request_id": "req-42", "editor_log_offset_bytes": self.offset}
            ],
        )

        self.assertEqual("anchor_log_mismatch", payload["since_anchor"]["resolved"])
        self.assertEqual(5, payload["match_count"])

    def test_an_offset_landing_mid_line_cannot_fabricate_a_match(self) -> None:
        """The editor records FileInfo.Length at a moment in time, so the offset can land inside a partially
        written line. Keeping the fragment lets a pattern match text the real line does not contain: an offset
        splitting "xxNOMARKER here" leaves "MARKER here", which a grep for MARKER reported as a hit on a line
        that literally says NOMARKER — with result_trust_class session_scoped_editor_log and an empty caveat.
        A false positive wearing a trust label is exactly what this retro exists to remove."""

        log = self.root / "midline.log"
        write_log(log, "L1aaaaaa\nxxNOMARKER here\nL3cccccc\n")

        payload = server_health.grep_editor_log_payload(
            self.root,
            log,
            pattern="MARKER",
            since="playmode_start",
            bridge_state={"editor_log_offset_at_playmode_start": 13, "editor_log_path": str(log)},
        )

        self.assertTrue(payload["since_anchor"]["starts_mid_line"])
        self.assertTrue(payload["since_anchor"]["partial_leading_line_dropped"])
        self.assertEqual(0, payload["match_count"], "the NOMARKER line must not be reported as a MARKER hit")

    def test_dropping_the_partial_line_advances_the_reported_start_line(self) -> None:
        log = self.root / "midline2.log"
        write_log(log, "L1aaaaaaa\nL2bbbbbbb\nL3MARKERc\nL4ddddddd\nL5MARKERe\n")

        payload = server_health.grep_editor_log_payload(
            self.root,
            log,
            pattern="MARKER",
            since="playmode_start",
            bridge_state={"editor_log_offset_at_playmode_start": 22, "editor_log_path": str(log)},
        )

        self.assertEqual(4, payload["searched_from_line"], "line 3 was partial and dropped")
        self.assertEqual([5], [item["line"] for item in payload["items"]])

    def test_a_crlf_log_anchors_on_real_byte_offsets(self) -> None:
        """Unity writes CRLF on Windows. Both sides of the anchor deal in real bytes - the editor stamps
        FileInfo.Length, the host seeks to that byte - and a CRLF line still carries exactly one b"\n", so the
        line counter stays right. This case exists because the LF-only fixtures passed on macOS while the
        Windows CI leg failed: the tests, not the product, were assuming LF."""

        log = self.root / "crlf.log"
        stale = write_log(log, "hook fired MARKER\n" * 3, newline="\r\n")
        write_log(log, "hook fired MARKER\n" * 5, newline="\r\n")

        payload = server_health.grep_editor_log_payload(
            self.root,
            log,
            pattern="MARKER",
            since="playmode_start",
            bridge_state={"editor_log_offset_at_playmode_start": len(stale), "editor_log_path": str(log)},
        )

        self.assertEqual(57, len(stale), "three CRLF lines are 19 bytes each, not 18")
        self.assertEqual(2, payload["match_count"])
        self.assertFalse(payload["since_anchor"]["starts_mid_line"])
        self.assertEqual(4, payload["searched_from_line"])
        self.assertEqual([4, 5], [item["line"] for item in payload["items"]])

    def test_a_crlf_offset_landing_mid_line_still_drops_the_fragment(self) -> None:
        log = self.root / "crlf_mid.log"
        write_log(log, "L1aaaaaa\nxxNOMARKER here\nL3cccccc\n", newline="\r\n")

        payload = server_health.grep_editor_log_payload(
            self.root,
            log,
            pattern="MARKER",
            since="playmode_start",
            bridge_state={"editor_log_offset_at_playmode_start": 14, "editor_log_path": str(log)},
        )

        self.assertTrue(payload["since_anchor"]["starts_mid_line"])
        self.assertEqual(0, payload["match_count"], "the NOMARKER line must not be reported as a MARKER hit")

    def test_an_offset_on_a_line_boundary_keeps_the_whole_first_line(self) -> None:
        log = self.root / "boundary.log"
        write_log(log, "L1aaaaaaa\nL2bbbbbbb\nL3MARKERc\nL4ddddddd\nL5MARKERe\n")

        payload = server_health.grep_editor_log_payload(
            self.root,
            log,
            pattern="MARKER",
            since="playmode_start",
            bridge_state={"editor_log_offset_at_playmode_start": 20, "editor_log_path": str(log)},
        )

        self.assertFalse(payload["since_anchor"]["starts_mid_line"])
        self.assertNotIn("partial_leading_line_dropped", payload["since_anchor"])
        self.assertEqual([3, 5], [item["line"] for item in payload["items"]])

    def test_a_truncated_grep_scope_keeps_anchor_adjacent_absolute_line_numbers(self) -> None:
        """An anchored grep keeps the head of its scope, so its first line is still the anchor's absolute line."""

        log = self.root / "big.log"
        write_log(log, "".join(f"line{n:05d} " + "x" * 38 + "\n" for n in range(1, 2001)))

        payload = server_health.grep_editor_log_payload(
            self.root,
            log,
            pattern="line0",
            since="playmode_start",
            limit=3,
            max_chars=2000,
            bridge_state={"editor_log_offset_at_playmode_start": 500, "editor_log_path": str(log)},
        )
        anchor = payload["since_anchor"]

        self.assertTrue(anchor["scope_truncated"])
        self.assertEqual("anchor_adjacent_head", payload["search_window_direction"])
        self.assertEqual("editor_log_absolute", payload["line_numbering_basis"])
        self.assertGreater(payload["searched_from_line"], 1)
        self.assertNotIn("anchor_line", anchor)

    def test_tail_honours_the_same_anchor(self) -> None:
        payload = server_health.tail_editor_log_payload(
            self.root,
            self.log,
            limit=10,
            since="playmode_start",
            bridge_state=self.bridge_state,
        )

        self.assertEqual(2, payload["tail_count"])
        self.assertEqual(4, payload["items"][0]["line"])
        self.assertEqual("session_scoped_editor_log", payload["result_trust_class"])

    def test_a_truncated_tail_keeps_the_recent_end_of_the_anchored_scope(self) -> None:
        log = self.root / "big-tail.log"
        prefix = "previous session\n"
        scope = "early MARKER\n" + "noise\n" * 100 + "late MARKER\n"
        write_log(log, prefix + scope)

        payload = server_health.tail_editor_log_payload(
            self.root,
            log,
            limit=10,
            max_chars=100,
            since="playmode_start",
            bridge_state={"editor_log_offset_at_playmode_start": len(prefix), "editor_log_path": str(log)},
        )

        self.assertEqual("scope_tail", payload["since_anchor"]["search_window_direction"])
        self.assertEqual("anchored_scope_relative", payload["line_numbering_basis"])
        self.assertIn("late MARKER", [item["message"] for item in payload["items"]])
        self.assertNotIn("early MARKER", [item["message"] for item in payload["items"]])

    def test_both_console_tools_expose_the_anchor(self) -> None:
        for tool_name in ("unity_console_grep", "unity_console_tail"):
            with self.subTest(tool=tool_name):
                schema = server_specs.TOOLS[tool_name]["inputSchema"]["properties"]
                self.assertIn("since", schema)
                self.assertEqual(list(server_health.SINCE_ANCHORS), schema["since"]["enum"])


class AnchorStateResolutionIsBestEffortTests(unittest.TestCase):
    """Reading an Editor.log must not start requiring a resolvable Unity project context.

    The log is path-backed, and the console tools are exactly what an operator reaches for when the project is
    in a bad state. Resolving a `since` anchor needs bridge state, but that lookup is best-effort: an
    unresolvable project context degrades to an unanchored search, which the payload already reports.
    """

    def _modules(self):
        import server_batch_orchestrator
        import server_cli_bridge_commands

        return (
            ("server_batch_orchestrator", server_batch_orchestrator),
            ("server_cli_bridge_commands", server_cli_bridge_commands),
        )

    def test_no_anchor_requested_never_touches_the_project_context(self) -> None:
        for name, module in self._modules():
            with self.subTest(module=name):
                self.assertEqual(
                    ({}, {}, True), module.editor_log_anchor_state("/definitely/not/a/unity/project", "")
                )

    def test_an_unresolvable_project_context_degrades_instead_of_raising(self) -> None:
        for name, module in self._modules():
            with self.subTest(module=name):
                self.assertEqual(
                    ({}, {}, True),
                    module.editor_log_anchor_state("/definitely/not/a/unity/project", "playmode_start"),
                )

    def test_the_journal_lookup_branch_actually_executes_in_both_entrypoints(self) -> None:
        """Executes the branch, not just the early return.

        `server_cli_bridge_commands` is a `from server_cli_shared import *` module, so a name the helper body
        needs but the star-import does not re-export is a latent NameError on an untested branch. That is exactly
        what shipped here: a 738-test suite stayed green while the live CLI raised
        `NameError: read_request_journal_events`. Asserting the early return is not enough — the call must reach
        the journal read.
        """

        for name, module in self._modules():
            with self.subTest(module=name):
                self.assertEqual(
                    [],
                    module.editor_log_anchor_journal(Path("/definitely/not/a/unity/project"), "request_id", "req-1"),
                )

    def test_the_journal_lookup_is_skipped_for_every_other_anchor(self) -> None:
        for name, module in self._modules():
            for since in ("", "playmode_start", "bridge_generation"):
                with self.subTest(module=name, since=since):
                    self.assertEqual([], module.editor_log_anchor_journal(Path("/nope"), since, "req-1"))

    def test_the_anchor_state_reports_whether_its_editor_is_still_alive(self) -> None:
        """Executes the real read, not a stub: read_best_effort_bridge_state already refuses a dead pid, and the
        project-context fallback deliberately keeps serving that stale state for diagnosis, so the anchor path
        has to carry liveness itself. A dead session's offsets were measured against a log Unity has truncated.
        """

        import os

        import server_bridge_paths

        for name, module in self._modules():
            with TemporaryDirectory() as tmp:
                root = Path(tmp) / "Proj"
                (root / "Assets").mkdir(parents=True)
                (root / "ProjectSettings").mkdir()
                (root / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.0.58f2\n")
                state_path = server_bridge_paths.bridge_state_path(root)
                state_path.parent.mkdir(parents=True, exist_ok=True)

                for label, pid, expected_live in (("dead", 999999, False), ("live", os.getpid(), True)):
                    with self.subTest(module=name, editor=label):
                        state_path.write_text(
                            json.dumps(
                                {
                                    "editor_pid": pid,
                                    "editor_log_offset_at_playmode_start": 250_000,
                                    "editor_log_path": str(root / "Logs" / "Editor.log"),
                                }
                            )
                        )
                        _, _, is_live = module.editor_log_anchor_state(root, "playmode_start")
                        self.assertEqual(expected_live, is_live)

    def test_an_absent_bridge_state_is_not_reported_as_a_dead_session(self) -> None:
        """Absence must keep degrading to anchor_unavailable; only a state file whose editor is gone is stale."""

        import server_bridge_paths

        for name, module in self._modules():
            with TemporaryDirectory() as tmp:
                root = Path(tmp) / "Proj"
                (root / "Assets").mkdir(parents=True)
                (root / "ProjectSettings").mkdir()
                (root / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.0.58f2\n")
                self.assertFalse(server_bridge_paths.bridge_state_path(root).exists())

                with self.subTest(module=name):
                    bridge_state, _, is_live = module.editor_log_anchor_state(root, "playmode_start")
                    self.assertEqual({}, bridge_state)
                    self.assertTrue(is_live)

    def test_both_entrypoints_share_one_helper_rather_than_duplicating_it(self) -> None:
        import server_batch_orchestrator
        import server_cli_bridge_commands

        for helper in ("editor_log_anchor_state", "editor_log_anchor_journal"):
            with self.subTest(helper=helper):
                self.assertIs(
                    getattr(server_batch_orchestrator, helper),
                    getattr(server_cli_bridge_commands, helper),
                )


class EditorLogLaneTests(unittest.TestCase):
    """Which file the host opens is the oldest unfixed root cause on this surface.

    The host default only holds for editors it launched with `-logFile`. Measured on a live consumer project: a
    `healthy` heartbeat, a default log untouched for 12 hours, and the editor writing a different file — and grep
    happily returned a match from the stale one with no staleness signal at all.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "Library" / "XUUnityLightMcp" / "logs").mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._tmp.cleanup)

    def host_default(self) -> Path:
        return self.root / "Library" / "XUUnityLightMcp" / "logs" / "unity_editor.log"

    def test_a_live_editor_writing_elsewhere_makes_the_default_lane_stale(self) -> None:
        default_log = self.host_default()
        write_log(default_log, "a line from a previous session\n")
        os.utime(default_log, (time.time() - 43_200, time.time() - 43_200))
        real_log = self.root / "Editor.log"
        write_log(real_log, "the line the editor is writing now\n")

        lane = server_health.build_editor_log_lane(
            self.root,
            default_log,
            bridge_state={
                "editor_log_path": str(real_log),
                "heartbeat_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "editor_pid": 4242,
            },
            editor_is_live=True,
        )

        self.assertEqual("stale_not_written_by_live_editor", lane["lane"])
        self.assertGreater(lane["editor_log_age_seconds"], 3600)
        self.assertIn("editorLogPath", lane["recommended_next_action"])

    def test_an_idle_editor_on_its_own_log_is_not_called_stale(self) -> None:
        default_log = self.host_default()
        write_log(default_log, "quiet but correct\n")

        lane = server_health.build_editor_log_lane(
            self.root,
            default_log,
            bridge_state={
                "editor_log_path": str(default_log),
                "heartbeat_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            editor_is_live=True,
        )

        self.assertEqual("host_owned_logfile", lane["lane"])

    def test_the_host_prefers_the_log_a_live_editor_reports(self) -> None:
        real_log = self.root / "Editor.log"
        write_log(real_log, "editor output\n")

        resolved = server_editor_host_paths.resolve_editor_log_path(
            self.root,
            None,
            bridge_state={"editor_log_path": str(real_log)},
        )

        self.assertEqual(real_log.resolve(), resolved)

    def test_an_explicit_path_still_wins_over_the_reported_one(self) -> None:
        real_log = self.root / "Editor.log"
        write_log(real_log, "editor output\n")
        chosen = self.root / "chosen.log"
        write_log(chosen, "operator's choice\n")

        resolved = server_editor_host_paths.resolve_editor_log_path(
            self.root,
            str(chosen),
            bridge_state={"editor_log_path": str(real_log)},
        )

        self.assertEqual(chosen.resolve(), resolved)

    def test_a_reported_log_that_does_not_exist_falls_back_to_the_default(self) -> None:
        resolved = server_editor_host_paths.resolve_editor_log_path(
            self.root,
            None,
            bridge_state={"editor_log_path": str(self.root / "gone.log")},
        )

        self.assertEqual(self.host_default().resolve(), resolved.resolve())


class RotatedLogForwardResolutionTests(unittest.TestCase):
    """`anchor_log_rotated` fails closed, which was right but unactionable: its own advice (search the sibling)
    then tripped `anchor_log_mismatch`, so on a two-editor host neither path anchored. Forward-resolve instead."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_rotated_stamp_resolves_forward_onto_the_sibling(self) -> None:
        # The stamped path holds the other editor's log, untouched since before the stamp; the sibling is the
        # file this editor kept writing through its open handle after Unity renamed it.
        stamp_epoch = time.time() - 600
        stamped = self.root / "Editor.log"
        write_log(stamped, "the other editor's output\n")
        os.utime(stamped, (stamp_epoch - 43_200, stamp_epoch - 43_200))
        sibling = self.root / "Editor-prev.log"
        prefix = "before the stamp\n"
        write_log(sibling, prefix + "after the stamp\n")

        anchor = server_health.resolve_editor_log_since_anchor(
            stamped,
            since="playmode_start",
            bridge_state={
                "editor_log_offset_at_playmode_start": len(prefix.encode("utf-8")),
                "editor_log_playmode_started_utc": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(stamp_epoch)
                ),
                "editor_log_path": str(stamped),
            },
        )

        self.assertTrue(anchor["anchored"])
        self.assertEqual(str(sibling), anchor["forward_resolved_editor_log_path"])
        self.assertEqual(sibling, server_health.effective_editor_log_path(stamped, anchor))

    def test_searching_the_sibling_directly_is_not_a_mismatch(self) -> None:
        stamped = self.root / "Editor.log"
        write_log(stamped, "other editor\n")
        sibling = self.root / "Editor-prev.log"
        prefix = "before\n"
        write_log(sibling, prefix + "after\n")

        anchor = server_health.resolve_editor_log_since_anchor(
            sibling,
            since="playmode_start",
            bridge_state={
                "editor_log_offset_at_playmode_start": len(prefix.encode("utf-8")),
                "editor_log_playmode_started_utc": "2020-01-01T00:00:00Z",
                "editor_log_path": str(stamped),
            },
        )

        self.assertNotEqual("anchor_log_mismatch", anchor["resolved"])
        self.assertTrue(anchor["anchored"])

    def test_the_rotated_sibling_is_a_discovery_candidate(self) -> None:
        names = [path.name for path in server_health.platform_editor_log_candidates()]

        self.assertTrue(any(name.endswith("-prev.log") for name in names), names)


class CliCommandBindingTests(unittest.TestCase):
    """Every registered subcommand must resolve to a callable.

    `request-console-tail` was registered in the parser and documented on the CLI, including its new `--since`
    anchors, but `cmd_request_console_tail` was never re-exported by `server_cli_commands`. build_parser() binds
    `func` only when getattr finds the name, so the command silently fell through to `parser.print_help()` and
    exited 1 -- a documented lane that had never run. A name-by-name export list cannot be trusted by review; it
    has to be swept.
    """

    def test_every_subcommand_resolves_to_a_callable(self) -> None:
        import argparse

        import server_cli_commands
        import server_cli_parser

        parser = server_cli_parser.build_parser()
        unbound = []
        for action in parser._actions:
            if not isinstance(action, argparse._SubParsersAction):
                continue
            for name, command_parser in action.choices.items():
                func_name = command_parser.get_default("func_name")
                if not func_name:
                    continue
                if getattr(server_cli_commands, func_name, None) is None:
                    unbound.append(f"{name} -> {func_name}")

        self.assertEqual([], unbound, "these subcommands print help and exit 1 instead of running")


class AnchorTrustBoundaryTests(unittest.TestCase):
    """The three ways an anchored result could still lie, each found by review after the feature shipped."""

    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        self.root = Path(self._temp.name)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_anchor_from_previous_editor_process_cannot_produce_a_negative_verdict(self) -> None:
        log = self.root / "Editor.log"
        prefix = "previous session\n"
        write_log(log, prefix + "current session without marker\n")

        payload = server_health.grep_editor_log_payload(
            self.root,
            log,
            pattern="ABSENT",
            since="playmode_start",
            bridge_state={
                "editor_pid": 222,
                "editor_log_offset_at_playmode_start": len(prefix),
                "editor_log_playmode_anchor_editor_pid": 111,
                "editor_log_path": str(log),
            },
        )

        self.assertEqual("anchor_process_mismatch", payload["since_anchor"]["resolved"])
        self.assertFalse(payload["since_anchor"]["anchored"])
        self.assertTrue(payload["since_anchor_degraded"])
        self.assertNotEqual("not_matched", payload["search_verdict"])

    def test_an_anchor_adjacent_cut_cannot_fabricate_a_regex_match(self) -> None:
        """Cutting `ERRORDETAIL` after `ERROR` must not make an `ERROR$` regex match a line that never ended."""

        log = self.root / "Editor.log"
        prefix = "previous session\n"
        complete = "early complete\n"
        scope = complete + "ERRORDETAIL\nlate line\n"
        max_chars = len(complete + "ERROR")
        write_log(log, prefix + scope)

        payload = server_health.grep_editor_log_payload(
            self.root,
            log,
            pattern="ERROR$",
            regex=True,
            since="playmode_start",
            max_chars=max_chars,
            bridge_state={"editor_log_offset_at_playmode_start": len(prefix), "editor_log_path": str(log)},
        )

        self.assertTrue(payload["since_anchor"]["scope_truncated"])
        self.assertFalse(payload["since_anchor"]["starts_mid_line"], "the anchor itself is on a line boundary")
        self.assertTrue(payload["since_anchor"]["partial_trailing_line_dropped"])
        self.assertEqual(0, payload["match_count"])
        self.assertEqual([], [item["message"] for item in payload["items"]])

    def test_anchor_adjacent_window_finds_an_early_boot_marker(self) -> None:
        """The fixed window belongs at the anchor: boot evidence must not be displaced by a long later scope."""

        log = self.root / "Editor.log"
        prefix = "previous session\n"
        early = "BOOT MARKER\n"
        scope = early + "noise\n" * 200 + "late line\n"
        max_chars = len(early + "noise\n" * 3)
        write_log(log, prefix + scope)

        payload = server_health.grep_editor_log_payload(
            self.root,
            log,
            pattern="BOOT MARKER",
            since="playmode_start",
            max_chars=max_chars,
            bridge_state={"editor_log_offset_at_playmode_start": len(prefix), "editor_log_path": str(log)},
        )

        self.assertTrue(payload["since_anchor"]["scope_truncated"])
        self.assertEqual("anchor_adjacent_head", payload["search_window_direction"])
        self.assertEqual("matched", payload["search_verdict"])
        self.assertEqual(["BOOT MARKER"], [item["message"] for item in payload["items"]])

    def test_a_partial_zero_match_is_explicitly_inconclusive(self) -> None:
        log = self.root / "Editor.log"
        prefix = "previous session\n"
        scope = "early line\n" + "noise\n" * 200 + "LATE MARKER\n"
        write_log(log, prefix + scope)

        payload = server_health.grep_editor_log_payload(
            self.root,
            log,
            pattern="LATE MARKER",
            since="playmode_start",
            max_chars=100,
            bridge_state={"editor_log_offset_at_playmode_start": len(prefix), "editor_log_path": str(log)},
        )

        self.assertEqual(0, payload["match_count"])
        self.assertTrue(payload["scope_truncated"])
        self.assertEqual("inconclusive", payload["search_verdict"])
        self.assertEqual("anchored_scope_truncated_before_full_search", payload["search_verdict_reason"])
        self.assertEqual("session_scoped_editor_log_partial_scope", payload["result_trust_class"])
        self.assertEqual(
            server_health.EDITOR_LOG_PARTIAL_SCOPE_RECOVERY_ACTION,
            payload["recommended_next_action"],
        )

    def test_the_truncation_flag_is_the_readers_own_verdict_not_a_byte_estimate(self) -> None:
        """`scoped_bytes_available > max_chars` compared bytes against a char budget, so a multi-byte scope
        flipped the flag while the reader had not truncated, discarding recoverable absolute line numbers."""

        log = self.root / "Editor.log"
        prefix = "previous session\n"
        body = "".join("МАРКЕР строка\n" for _ in range(20))
        write_log(log, prefix + body)
        self.assertGreater(len(body.encode("utf-8")), 400, "fixture must exceed the budget in bytes")
        self.assertLess(len(body), 400, "fixture must stay inside the budget in characters")

        payload = server_health.grep_editor_log_payload(
            self.root,
            log,
            pattern="МАРКЕР",
            since="playmode_start",
            max_chars=400,
            limit=50,
            bridge_state={"editor_log_offset_at_playmode_start": len(prefix.encode("utf-8"))},
        )

        self.assertFalse(payload["since_anchor"]["scope_truncated"])
        self.assertEqual("editor_log_absolute", payload["line_numbering_basis"])
        self.assertEqual(2, payload["items"][0]["line"])

    def test_tail_line_numbers_survive_blank_lines(self) -> None:
        """Filtering blank lines before numbering reported every item several lines early, under a payload that
        newly claims `editor_log_absolute`."""

        log = self.root / "Editor.log"
        prefix = "previous session\n"
        write_log(log, prefix + "alpha\n\n\n\nbravo MARKER\n")

        payload = server_health.tail_editor_log_payload(
            self.root,
            log,
            since="playmode_start",
            bridge_state={"editor_log_offset_at_playmode_start": len(prefix.encode("utf-8"))},
        )

        self.assertEqual("editor_log_absolute", payload["line_numbering_basis"])
        self.assertEqual(
            [(2, "alpha"), (6, "bravo MARKER")],
            [(item["line"], item["message"]) for item in payload["items"]],
        )

    def test_a_quiet_log_with_no_replacement_candidate_still_anchors(self) -> None:
        """Staleness alone is not rotation, and getting that wrong broke `since=` on any idle editor.

        Caught on a live project: a `request_started` stamped at 22:28:53Z against a log last written at
        22:21:38Z — the editor was alive and serving requests, it simply had not logged for seven minutes, and no
        `-prev` sibling existed. The first version of this guard called that a rotated path and refused the anchor.
        """

        log = self.root / "Editor.log"
        prefix = "quiet but still the writer\n"
        write_log(log, prefix + "a later line\n")
        os.utime(log, (1_700_000_000, 1_700_000_000))

        anchor = server_health.resolve_editor_log_since_anchor(
            log,
            since="playmode_start",
            bridge_state={
                "editor_log_offset_at_playmode_start": len(prefix.encode("utf-8")),
                # stamped long after the log was last touched
                "editor_log_playmode_started_utc": "2026-08-04T22:28:53Z",
                "editor_log_path": str(log),
            },
        )

        self.assertTrue(anchor["anchored"], "a quiet log is not a replaced log")
        self.assertNotEqual("anchor_log_rotated", anchor["resolved"])
        self.assertNotIn("forward_resolved_editor_log_path", anchor)

    def test_a_log_written_after_its_stamp_still_anchors(self) -> None:
        log = self.root / "Editor.log"
        prefix = "before the stamp\n"
        write_log(log, prefix + "after the stamp\n")

        anchor = server_health.resolve_editor_log_since_anchor(
            log,
            since="playmode_start",
            bridge_state={
                "editor_log_offset_at_playmode_start": len(prefix.encode("utf-8")),
                "editor_log_playmode_started_utc": "2020-01-01T00:00:00Z",
                "editor_log_path": str(log),
            },
        )

        self.assertTrue(anchor["anchored"], "a live log newer than its stamp must not be refused")

    def test_a_dead_editor_session_never_anchors(self) -> None:
        """bridge_state.json outlives its editor. Unity truncates Editor.log on start, so a dead session's
        offset points at an arbitrary byte of the new log once that log grows past it -- the failure that
        removed the session_start anchor, reachable again through the state-sourced anchors."""

        log = self.root / "Editor.log"
        size = len(write_log(log, "".join(f"new session line {index:06d}\n" for index in range(14000))))
        stale_offset = 250_000
        self.assertGreater(size, stale_offset, "the guard on file_size < offset must not be what refuses this")

        for since in ("playmode_start", "bridge_generation", "request_id"):
            with self.subTest(since=since):
                anchor = server_health.resolve_editor_log_since_anchor(
                    log,
                    since=since,
                    since_request_id="req-1",
                    journal_events=[
                        {
                            "event_type": "request_started",
                            "editor_log_offset_bytes": stale_offset,
                            "editor_log_path": str(log),
                        }
                    ],
                    bridge_state={
                        "editor_log_offset_at_playmode_start": stale_offset,
                        "editor_log_offset_at_bridge_generation_start": stale_offset,
                        "editor_log_path": str(log),
                        "editor_pid": 999999,
                    },
                    bridge_state_is_live=False,
                )

                self.assertFalse(anchor["anchored"])
                self.assertEqual("anchor_stale_dead_session", anchor["resolved"])
                self.assertIn("recover-editor-session", anchor["recommended_next_action"])

    def test_a_live_editor_session_still_anchors(self) -> None:
        log = self.root / "Editor.log"
        prefix = "previous session\n"
        write_log(log, prefix + "fresh MARKER\n")

        anchor = server_health.resolve_editor_log_since_anchor(
            log,
            since="playmode_start",
            bridge_state={
                "editor_log_offset_at_playmode_start": len(prefix.encode("utf-8")),
                "editor_log_path": str(log),
            },
            bridge_state_is_live=True,
        )

        self.assertTrue(anchor["anchored"])
        self.assertEqual("playmode_start", anchor["resolved"])

    def test_a_request_id_offset_carries_its_own_log_identity(self) -> None:
        """`recover-editor-session` unlinks bridge_state.json and leaves the journal, so an offset that had no
        identity of its own anchored against whatever log the host happened to resolve."""

        log = self.root / "Editor.log"
        prefix = "previous session\n"
        write_log(log, prefix + "fresh MARKER\n")

        anchor = server_health.resolve_editor_log_since_anchor(
            log,
            since="request_id",
            since_request_id="req-1",
            bridge_state={},
            journal_events=[
                {
                    "event_type": "request_started",
                    "editor_log_offset_bytes": len(prefix.encode("utf-8")),
                    "editor_log_path": str(log),
                }
            ],
        )

        self.assertTrue(anchor["anchored"])
        self.assertEqual(str(log), anchor.get("journal_editor_log_path", str(log)))

    def test_a_request_id_offset_without_any_log_identity_is_refused(self) -> None:
        log = self.root / "Editor.log"
        write_log(log, "".join(f"line {index:05d}\n" for index in range(1000)))

        anchor = server_health.resolve_editor_log_since_anchor(
            log,
            since="request_id",
            since_request_id="req-1",
            bridge_state={},
            journal_events=[{"event_type": "request_started", "editor_log_offset_bytes": 4000}],
        )

        self.assertFalse(anchor["anchored"])
        self.assertEqual("anchor_identity_unverified", anchor["resolved"])

    def test_a_request_id_offset_stamped_against_another_log_is_refused(self) -> None:
        """Same refusal as the bridge_state path, now reachable without a bridge_state at all."""

        log = self.root / "Editor.log"
        write_log(log, "".join(f"line {index:05d}\n" for index in range(1000)))

        anchor = server_health.resolve_editor_log_since_anchor(
            log,
            since="request_id",
            since_request_id="req-1",
            bridge_state={},
            journal_events=[
                {
                    "event_type": "request_started",
                    "editor_log_offset_bytes": 4000,
                    "editor_log_path": str(self.root / "Some-Other-Editor.log"),
                }
            ],
        )

        self.assertFalse(anchor["anchored"])
        self.assertEqual("anchor_log_mismatch", anchor["resolved"])

    def test_the_editor_stamps_the_log_path_beside_the_offset(self) -> None:
        journal = read_source("Bridge/XUUnityLightMcpRequestJournal.cs")
        anchors = read_source("Bridge/XUUnityLightMcpEditorLogAnchors.cs")
        models = read_source("Core/XUUnityLightMcpBridgeModels.cs")

        self.assertIn("editor_log_path = XUUnityLightMcpEditorLogAnchors.CurrentEditorLogPath()", journal)
        self.assertIn("public static string CurrentEditorLogPath()", anchors)
        self.assertIn("public string editor_log_path = \"\";", models)

    def test_the_since_description_never_advertises_an_anchor_the_enum_rejects(self) -> None:
        """A `session_start` anchor was implemented and then removed, but both tool descriptions kept promising
        it -- a contradiction inside one schema, and a guaranteed wasted call for an operator who believes it."""

        for tool_name in ("unity_console_grep", "unity_console_tail"):
            with self.subTest(tool=tool_name):
                since = server_specs.TOOLS[tool_name]["inputSchema"]["properties"]["since"]
                self.assertEqual(list(server_health.SINCE_ANCHORS), since["enum"])
                self.assertNotIn("session_start", since["description"])
                for anchor_name in server_health.SINCE_ANCHORS:
                    self.assertIn(anchor_name, since["description"])


class RequestAttributionTests(unittest.TestCase):
    def test_the_operators_own_cli_run_does_not_raise_the_foreign_client_alarm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            server_bridge_journal.write_host_request_journal_event(
                root,
                "request_submitted",
                {
                    "request_submitted_unix": time.time(),
                    "client_session_id": "operator-cli-process",
                    "client_kind": server_bridge_journal.HOST_CLIENT_KIND_CLI,
                },
            )
            summary = server_bridge_journal.summarize_request_attribution(root)

        self.assertEqual(0, summary["foreign_requests_since_client_start"])
        self.assertFalse(summary["foreign_request_activity_detected"])
        self.assertEqual("", summary["last_foreign_request_at_utc"])
        self.assertEqual(1, summary["cli_requests_since_client_start"])
        self.assertTrue(summary["cli_request_activity_detected"])
        self.assertNotEqual("", summary["last_cli_request_at_utc"])

    def test_a_second_long_lived_client_session_still_raises_the_alarm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            server_bridge_journal.write_host_request_journal_event(
                root,
                "request_submitted",
                {
                    "request_submitted_unix": time.time(),
                    "client_session_id": "another-agent-session",
                    "client_kind": server_bridge_journal.HOST_CLIENT_KIND_MCP_SERVER,
                },
            )
            summary = server_bridge_journal.summarize_request_attribution(root)

        self.assertEqual(1, summary["foreign_requests_since_client_start"])
        self.assertTrue(summary["foreign_request_activity_detected"])
        self.assertNotEqual("", summary["last_foreign_request_at_utc"])
        self.assertEqual(0, summary["cli_requests_since_client_start"])
        self.assertFalse(summary["cli_request_activity_detected"])

    def test_a_journal_row_written_before_client_kind_existed_still_classifies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            journal_dir = server_bridge_paths.request_journal_dir(root)
            journal_dir.mkdir(parents=True, exist_ok=True)
            server_core.write_json(
                journal_dir / "legacy_attributed_request_submitted.json",
                {
                    "event_type": "request_submitted",
                    "event_at_utc": "2026-09-04T00:00:00Z",
                    "request_submitted_unix": time.time(),
                    "client_session_id": "older-host-version",
                },
            )
            server_core.write_json(
                journal_dir / "legacy_unattributed_request_submitted.json",
                {
                    "event_type": "request_submitted",
                    "event_at_utc": "2026-09-04T00:00:00Z",
                    "request_submitted_unix": time.time(),
                },
            )
            summary = server_bridge_journal.summarize_request_attribution(root)

        self.assertEqual(1, summary["foreign_requests_since_client_start"])
        self.assertTrue(summary["foreign_request_activity_detected"])
        self.assertEqual(1, summary["unattributed_requests_since_client_start"])
        self.assertEqual(0, summary["cli_requests_since_client_start"])

    def test_the_host_publishes_its_client_session_id_to_child_host_processes(self) -> None:
        self.assertEqual(
            server_bridge_journal.current_client_session_id(),
            os.environ.get("XUUNITY_CLIENT_SESSION_ID"),
        )

    def test_the_cli_entrypoint_marks_its_client_kind(self) -> None:
        previous_kind = server_bridge_journal.current_client_kind()
        self.addCleanup(server_bridge_journal.mark_host_client_kind, previous_kind)
        server_bridge_journal.mark_host_client_kind(server_bridge_journal.HOST_CLIENT_KIND_CLI)
        self.assertEqual("cli", server_bridge_journal.current_client_kind())

        with tempfile.TemporaryDirectory() as temp_dir:
            path = server_bridge_journal.write_host_request_journal_event(
                Path(temp_dir),
                "request_submitted",
                {"request_submitted_unix": time.time()},
            )
            self.assertEqual("cli", server_core.read_json(path)["client_kind"])

        self.assertIn(
            "mark_host_client_kind(HOST_CLIENT_KIND_CLI)",
            (TEMPLATES_DIR / "server.py").read_text(encoding="utf-8"),
        )

    def test_status_counter_distinguishes_own_foreign_and_unattributed_requests(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            server_bridge_journal.write_host_request_journal_event(
                root,
                "request_submitted",
                {
                    "request_submitted_unix": time.time(),
                    "client_session_id": server_bridge_journal.current_client_session_id(),
                },
            )
            server_bridge_journal.write_host_request_journal_event(
                root,
                "request_submitted",
                {"request_submitted_unix": time.time(), "client_session_id": "another-client"},
            )
            server_bridge_journal.write_host_request_journal_event(
                root,
                "request_submitted",
                {"request_submitted_unix": time.time(), "client_session_id": ""},
            )
            server_bridge_journal.write_host_request_journal_event(
                root,
                "request_submitted",
                {
                    "request_submitted_unix": "malformed",
                    "event_at_utc": "1970-01-01T00:00:00Z",
                    "client_session_id": "old-client",
                },
            )

            summary = server_bridge_journal.summarize_request_attribution(root)

        self.assertEqual(1, summary["own_requests_since_client_start"])
        self.assertEqual(1, summary["foreign_requests_since_client_start"])
        self.assertEqual(1, summary["unattributed_requests_since_client_start"])
        self.assertTrue(summary["foreign_request_activity_detected"])


class PostSettleCompileTrustTests(unittest.TestCase):
    """A refresh that settles during Play Mode defers asset import, so its compile verdict is not authoritative."""

    def _refresh(self, playmode_state: str, *, is_playing: bool) -> dict:
        return server_bridge_payloads.normalize_refresh_payload_from_lifecycle(
            {"outcome": "refresh_completed", "settle_request_id": "req-1"},
            {
                "operation": "unity.project.refresh",
                "idle_wait_after": {
                    "heartbeat_utc": "2026-08-03T10:00:00Z",
                    "is_compiling": False,
                    "is_updating": False,
                    "is_playing": is_playing,
                    "playmode_state": playmode_state,
                    "compiler_error_count": 0,
                    "script_compilation_failed": False,
                    "recent_compiler_diagnostics": [],
                },
            },
        )

    def test_refresh_in_edit_mode_is_a_confirmed_green(self) -> None:
        payload = self._refresh("edit", is_playing=False)

        self.assertEqual("passed", payload["post_settle_compile"])
        self.assertEqual("confirmed", payload["post_settle_compile_trust_class"])

    def test_refresh_during_playmode_marks_the_green_as_deferred(self) -> None:
        payload = self._refresh("playing", is_playing=True)

        self.assertEqual("passed", payload["post_settle_compile"])
        self.assertEqual("deferred_during_playmode", payload["post_settle_compile_trust_class"])
        self.assertIn("not authoritative", payload["post_settle_compile_note"])
        self.assertEqual("exit_play_mode_then_rerun_refresh", payload["post_settle_compile_recommended_next_action"])

    def test_a_playmode_test_run_is_not_mislabelled_as_deferred(self) -> None:
        payload = server_bridge_payloads.normalize_tests_payload_from_lifecycle(
            {"status": "completed"},
            {
                "operation": "unity.tests.run_playmode",
                "idle_wait_after": {
                    "is_compiling": False,
                    "is_updating": False,
                    "is_playing": True,
                    "playmode_state": "playing",
                    "compiler_error_count": 0,
                    "script_compilation_failed": False,
                    "recent_compiler_diagnostics": [],
                },
            },
        )

        self.assertEqual("confirmed", payload["post_settle_compile_trust_class"])

    def test_test_result_accounting_preserves_callback_state_and_marks_host_settle_difference(self) -> None:
        payload = server_bridge_payloads.normalize_tests_payload_from_lifecycle(
            {
                "status": "passed",
                "playmode_state_after_settle": "playing",
                "playmode_state_after_test_callbacks": "playing",
                "playmode_state_after_settle_source": "unity_test_callbacks",
            },
            {
                "operation": "unity.tests.run_playmode",
                "idle_wait_after": {
                    "is_compiling": False,
                    "is_updating": False,
                    "is_playing": False,
                    "playmode_state": "edit",
                    "compiler_error_count": 0,
                    "script_compilation_failed": False,
                    "recent_compiler_diagnostics": [],
                },
            },
        )

        self.assertEqual("playing", payload["playmode_state_after_test_callbacks"])
        self.assertEqual("edit", payload["playmode_state_after_host_settle"])
        self.assertEqual("edit", payload["playmode_state_after_settle"])
        self.assertEqual("idle_wait_after", payload["playmode_state_after_settle_source"])
        self.assertFalse(payload["playmode_state_accounting_consistent"])
        self.assertIn("callbacks reported 'playing'", payload["playmode_state_accounting_note"])
        self.assertEqual("confirmed", payload["playmode_state_after_settle_trust_class"])

    def test_host_reconciles_written_test_result_without_changing_test_totals(self) -> None:
        with TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            request_id = "test-accounting"
            result_path = (
                project_root
                / "Library"
                / "XUUnityLightMcp"
                / "state"
                / "test_results"
                / f"{request_id}.json"
            )
            server_core.write_json(
                result_path,
                {
                    "request_id": request_id,
                    "response_handoff_state": "written",
                    "total": 4,
                    "passed": 4,
                    "failed": 0,
                    "playmode_state_after_settle": "playing",
                    "playmode_state_after_test_callbacks": "playing",
                },
            )
            payload = server_bridge_payloads.normalize_tests_payload_from_lifecycle(
                {
                    "status": "passed",
                    "playmode_state_after_settle": "playing",
                    "playmode_state_after_test_callbacks": "playing",
                },
                {
                    "operation": "unity.tests.run_playmode",
                    "bridge_identity_transition": {
                        "previous_bridge_generation": 4,
                        "current_bridge_generation": 5,
                        "reclassified_status": "settled_after_lifecycle_reset",
                    },
                    "idle_wait_after": {
                        "is_compiling": False,
                        "is_updating": False,
                        "is_playing": False,
                        "playmode_state": "edit",
                        "compiler_error_count": 0,
                        "script_compilation_failed": False,
                        "recent_compiler_diagnostics": [],
                    },
                },
            )

            outcome = server_batch_orchestrator.reconcile_persisted_test_result_after_lifecycle(
                project_root,
                request_id,
                "unity.tests.run_playmode",
                payload,
                wait_timeout_seconds=0,
            )
            persisted = server_core.read_json(result_path)

        self.assertEqual("reconciled", outcome)
        self.assertEqual(4, persisted["total"])
        self.assertEqual(4, persisted["passed"])
        self.assertEqual("playing", persisted["playmode_state_after_test_callbacks"])
        self.assertEqual("edit", persisted["playmode_state_after_host_settle"])
        self.assertEqual("edit", persisted["playmode_state_after_settle"])
        self.assertEqual("idle_wait_after", persisted["playmode_state_after_settle_source"])
        self.assertFalse(persisted["playmode_state_accounting_consistent"])
        self.assertTrue(payload["lifecycle_churn_observed"])
        self.assertTrue(persisted["lifecycle_churn_observed"])
        self.assertEqual("stale_risk", payload["playmode_state_after_settle_trust_class"])
        self.assertEqual("stale_risk", persisted["playmode_state_after_settle_trust_class"])
        self.assertIn("bridge identity changed", persisted["playmode_state_after_settle_note"])

        compact = server_bridge_payloads.compact_operation_payload(payload, "unity.tests.run_playmode")
        self.assertEqual("playing", compact["playmode_state_after_test_callbacks"])
        self.assertEqual("edit", compact["playmode_state_after_host_settle"])
        self.assertEqual("stale_risk", compact["playmode_state_after_settle_trust_class"])

    def test_the_trust_class_survives_the_compact_envelope(self) -> None:
        payload = self._refresh("playing", is_playing=True)

        compact = server_bridge_payloads.compact_operation_payload(payload, "unity.project.refresh")

        self.assertEqual("deferred_during_playmode", compact["post_settle_compile_trust_class"])
        self.assertIn("post_settle_compile_recommended_next_action", compact)


class StructuralCompileDiagnosticTests(unittest.TestCase):
    """Structural asmdef failures must outrank stale C# rows without reviving prior-session log errors."""

    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.log = self.root / "Editor.log"

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _refresh(
        self,
        *,
        prefix: str,
        current: str,
        diagnostics: list[dict],
        offset_override: int | None = None,
    ) -> dict:
        prefix_bytes = write_log(self.log, prefix)
        write_log(self.log, prefix + current)
        offset = len(prefix_bytes) if offset_override is None else offset_override
        return server_bridge_payloads.normalize_refresh_payload_from_lifecycle(
            {"outcome": "refresh_completed", "settle_request_id": "req-structural"},
            {
                "idle_wait_after": {
                    "heartbeat_utc": "2026-08-08T10:00:00Z",
                    "refresh_settle_phase": "settled",
                    "refresh_settle_request_id": "req-structural",
                    "is_compiling": False,
                    "is_updating": False,
                    "playmode_state": "edit",
                    "script_compilation_failed": True,
                    "compiler_error_count": len(diagnostics),
                    "recent_compiler_diagnostics": diagnostics,
                    "compiler_diagnostics_source": "compilation_pipeline",
                    "editor_log_path": str(self.log),
                    "editor_log_offset_at_bridge_generation_start": offset,
                    "editor_log_offset_bridge_generation": 42,
                }
            },
        )

    def test_current_structural_error_precedes_stale_csharp_diagnostic(self) -> None:
        payload = self._refresh(
            prefix="Assembly has duplicate references: PreviousSession\n",
            current=(
                "Assembly has duplicate references: UniTask\n"
                "Assembly has duplicate references: UniTask\n"
            ),
            diagnostics=[{"message": "Assets/Removed.cs(1,1): error CS0246: stale"}],
        )

        messages = [item["message"] for item in payload["post_settle_diagnostics"]]
        self.assertEqual("Assembly has duplicate references: UniTask", messages[0])
        self.assertNotIn("Assembly has duplicate references: PreviousSession", messages)
        self.assertIn("Assets/Removed.cs(1,1): error CS0246: stale", messages)
        self.assertEqual(1, payload["post_settle_structural_diagnostic_count"])
        self.assertEqual("assembly_definition_error", payload["post_settle_compile_failure_class"])
        self.assertEqual(
            "editor_log_bridge_generation_scope+compilation_pipeline",
            payload["post_settle_compiler_diagnostics_source"],
        )
        self.assertEqual(
            "session_scoped",
            payload["post_settle_structural_diagnostics_scope"]["trust_class"],
        )
        self.assertEqual(
            "inspect_asmdef_references_and_editor_log_before_cache_cleanup",
            payload["post_settle_compile_recommended_next_action"],
        )

        compact = server_bridge_payloads.compact_operation_payload(payload, "unity.project.refresh")
        self.assertEqual("assembly_definition_error", compact["post_settle_compile_failure_class"])
        self.assertEqual(1, compact["post_settle_structural_diagnostic_count"])
        self.assertEqual(
            "Assembly has duplicate references: UniTask",
            compact["post_settle_diagnostics"][0]["message"],
        )

    def test_unusable_anchor_refuses_to_promote_an_old_structural_error(self) -> None:
        payload = self._refresh(
            prefix="Assembly has duplicate references: PreviousSession\n",
            current="",
            diagnostics=[],
            offset_override=100_000,
        )

        self.assertEqual(0, payload["post_settle_structural_diagnostic_count"])
        self.assertEqual(
            "unscoped_refused",
            payload["post_settle_structural_diagnostics_scope"]["trust_class"],
        )
        self.assertEqual("compiler_diagnostics_unavailable", payload["post_settle_compile_failure_class"])
        self.assertEqual("DiagnosticUnavailable", payload["post_settle_diagnostics"][0]["type"])
        self.assertNotIn("PreviousSession", payload["post_settle_diagnostics"][0]["message"])

    def test_compile_and_test_envelopes_share_the_structural_diagnostic_contract(self) -> None:
        prefix = "bridge attached\n"
        offset = len(write_log(self.log, prefix))
        write_log(self.log, prefix + "Unable to resolve reference 'Missing.Assembly'\n")
        state = {
            "is_compiling": False,
            "is_updating": False,
            "script_compilation_failed": True,
            "compiler_error_count": 0,
            "recent_compiler_diagnostics": [],
            "editor_log_path": str(self.log),
            "editor_log_offset_at_bridge_generation_start": offset,
            "editor_log_offset_bridge_generation": 9,
        }

        compile_payload = server_bridge_payloads.normalize_compile_payload_from_lifecycle(
            {"settle_request_id": "compile-1"},
            {"idle_wait_after": dict(state)},
        )
        test_payload = server_bridge_payloads.normalize_tests_payload_from_lifecycle(
            {"status": "completed"},
            {"idle_wait_after": dict(state)},
        )

        for payload in (compile_payload, test_payload):
            with self.subTest(payload=payload):
                self.assertEqual("failed", payload["post_settle_compile"])
                self.assertEqual("assembly_definition_error", payload["post_settle_compile_failure_class"])
                self.assertEqual(
                    "asmdef_unresolved_reference",
                    payload["post_settle_diagnostics"][0]["failure_class"],
                )


class CompactEnvelopeTests(unittest.TestCase):
    """The hot interactive tools must be able to answer without spending the whole result budget."""

    def test_playmode_and_screenshot_are_compactable(self) -> None:
        for operation in ("unity.playmode.state", "unity.playmode.set", "unity.game_view.screenshot"):
            with self.subTest(operation=operation):
                self.assertIn(operation, server_bridge_payloads.COMPACT_OPERATION_PAYLOADS)

    def test_compact_compile_warning_evidence_handles_nested_and_matrix_payloads(self) -> None:
        warning = {
            "assembly_name": "Game.dll",
            "code": "CS0618",
            "severity": "warning",
            "message": "old API",
            "file": "Assets/A.cs",
            "line": 10,
            "column": 4,
        }
        direct = server_bridge_payloads.compact_operation_payload(
            {
                "result": {
                    "status": "passed",
                    "rebuilt_assembly_count": 6,
                    "cached_assembly_count": 64,
                    "rebuild_evidence_status": "measured",
                    "rebuild_evidence_basis": "compilation_pipeline_started_and_not_required_events",
                    "warning_count": 2,
                    "unique_warning_count": 1,
                    "warning_sample_limit": 20,
                    "warnings_truncated": False,
                    "warnings": [warning],
                    "output_directory": "/tmp/bulk",
                },
                "post_settle_compile": "passed",
            },
            "unity.compile.player_scripts",
        )
        matrix = server_bridge_payloads.compact_operation_payload(
            {
                "status": "passed",
                "rebuilt_assembly_count": 8,
                "cached_assembly_count": 130,
                "rebuild_evidence_status": "measured",
                "rebuild_evidence_basis": "per_configuration_compilation_pipeline_events",
                "total": 2,
                "passed": 2,
                "failed": 0,
                "skipped": 0,
                "warning_count": 2,
                "unique_warning_count": 1,
                "warning_sample_limit": 20,
                "warnings_truncated": False,
                "warnings": [warning],
                "results": [
                    {
                        "name": "Android",
                        "target": "Android",
                        "status": "passed",
                        "rebuilt_assembly_count": 6,
                        "cached_assembly_count": 64,
                        "rebuild_evidence_status": "measured",
                        "warning_count": 2,
                        "unique_warning_count": 1,
                        "warnings_truncated": False,
                        "warnings": [warning],
                        "output_directory": "/tmp/bulk",
                    },
                    {
                        "name": "iOS",
                        "target": "iOS",
                        "status": "passed",
                        "rebuilt_assembly_count": 2,
                        "cached_assembly_count": 66,
                        "rebuild_evidence_status": "measured",
                        "warning_count": 0,
                    },
                ],
            },
            "unity.compile.matrix",
        )

        self.assertEqual(2, direct["warning_count"])
        self.assertEqual(6, direct["rebuilt_assembly_count"])
        self.assertEqual(64, direct["cached_assembly_count"])
        self.assertEqual("measured", direct["rebuild_evidence_status"])
        self.assertEqual("CS0618", direct["warnings"][0]["code"])
        self.assertNotIn("output_directory", direct)
        self.assertEqual(2, matrix["warning_count"])
        self.assertEqual(1, matrix["unique_warning_count"])
        self.assertEqual(2, matrix["configuration_count"])
        self.assertEqual(8, matrix["rebuilt_assembly_count"])
        self.assertEqual(130, matrix["cached_assembly_count"])
        self.assertEqual(2, len(matrix["configuration_rebuild_evidence"]))
        self.assertFalse(matrix["configuration_rebuild_evidence_truncated"])
        self.assertEqual("Android", matrix["first_warning_configurations"][0]["name"])
        self.assertNotIn("output_directory", matrix["first_warning_configurations"][0])

    def test_compact_screenshot_keeps_the_decision_fields_and_drops_the_bulk(self) -> None:
        payload = {
            "capture_source": "game_view",
            "file_path": "/tmp/shot.png",
            "width": 1170,
            "height": 2532,
            "render_width": 1170,
            "render_height": 2532,
            "screen_width": 1080,
            "screen_height": 1920,
            "render_target_available": True,
            "render_target_differs_from_screen": True,
            "playmode_state": "playing",
            "playmode_loop_liveness": "throttled",
            "playmode_liveness_warning": "playmode_throttled_editor_unfocused",
            "playmode_liveness_remediation": "focus_the_unity_editor_or_set_interaction_mode_to_no_throttling",
            "result_trust_class": "playmode_throttled",
            "image_included": False,
            "image_requested": True,
            "image_omitted_reason": "payload_budget",
            "image_bytes": 184000,
            "image_budget_bytes": 48000,
            "recommended_next_action": "read_file_path_with_an_image_reader",
            "some_bulky_diagnostic_block": {"a": 1},
        }

        compact = server_bridge_payloads.compact_operation_payload(payload, "unity.game_view.screenshot")

        self.assertEqual("/tmp/shot.png", compact["file_path"])
        self.assertEqual("payload_budget", compact["image_omitted_reason"])
        self.assertEqual(1170, compact["render_width"])
        self.assertEqual(1080, compact["screen_width"])
        self.assertTrue(compact["render_target_differs_from_screen"])
        self.assertEqual("throttled", compact["playmode_loop_liveness"])
        self.assertEqual("playmode_throttled", compact["result_trust_class"])
        self.assertNotIn("some_bulky_diagnostic_block", compact)
        self.assertNotIn("image_base64", compact)

    def test_a_within_budget_inline_image_is_preserved(self) -> None:
        compact = server_bridge_payloads.compact_operation_payload(
            {"file_path": "/tmp/shot.png", "image_included": True, "image_base64": "aGk="},
            "unity.game_view.screenshot",
        )

        self.assertEqual("aGk=", compact["image_base64"])

    def test_compact_playmode_keeps_the_state_fields(self) -> None:
        compact = server_bridge_payloads.compact_operation_payload(
            {
                "playmode_state": "playing",
                "is_playing": True,
                "is_paused": False,
                "settle_phase": "settled",
                "noise": list(range(100)),
            },
            "unity.playmode.state",
        )

        self.assertEqual("playing", compact["playmode_state"])
        self.assertTrue(compact["is_playing"])
        self.assertNotIn("noise", compact)

    def test_compact_playmode_keeps_the_liveness_evidence(self) -> None:
        compact = server_bridge_payloads.compact_operation_payload(
            {
                "playmode_state": "playing",
                "is_playing": True,
                "playmode_frame_count": 4321,
                "playmode_frames_advanced_last_interval": 0,
                "playmode_frame_sample_interval_seconds": 2.01,
                "editor_application_focused": False,
                "playmode_loop_liveness": "throttled",
                "playmode_liveness_warning": "playmode_throttled_editor_unfocused",
                "playmode_liveness_remediation": "focus_the_unity_editor_or_set_interaction_mode_to_no_throttling",
                "result_trust_class": "playmode_throttled",
                "noise": list(range(100)),
            },
            "unity.playmode.state",
        )

        self.assertEqual("throttled", compact["playmode_loop_liveness"])
        self.assertEqual("playmode_throttled_editor_unfocused", compact["playmode_liveness_warning"])
        self.assertEqual(0, compact["playmode_frames_advanced_last_interval"])
        self.assertEqual(4321, compact["playmode_frame_count"])
        self.assertFalse(compact["editor_application_focused"])
        self.assertIn("playmode_liveness_remediation", compact)
        self.assertEqual("playmode_throttled", compact["result_trust_class"])
        self.assertNotIn("noise", compact)

    def test_the_compactable_tools_expose_the_opt_out(self) -> None:
        for tool_name in (
            "unity_playmode_state",
            "unity_playmode_set",
            "unity_game_view_screenshot",
            "unity_scene_open",
            "unity_scene_snapshot",
            "unity_game_view_configure",
            "unity_project_action_invoke",
        ):
            with self.subTest(tool=tool_name):
                properties = server_specs.TOOLS[tool_name]["inputSchema"]["properties"]
                self.assertIn("includeFullPayload", properties)
                self.assertFalse(properties["includeFullPayload"]["default"])

    def test_scene_and_view_operations_are_compactable(self) -> None:
        for operation in ("unity.scene.open", "unity.scene.snapshot", "unity.game_view.configure"):
            with self.subTest(operation=operation):
                self.assertIn(operation, server_bridge_payloads.COMPACT_OPERATION_PAYLOADS)

    def test_compact_scene_open_keeps_the_scene_transition_and_drops_the_lifecycle(self) -> None:
        payload = {
            "status": "ok",
            "opened": True,
            "outcome": "scene_opened",
            "requested_scene_path": "Assets/Scenes/Boot.unity",
            "allow_dirty_scene_discard": False,
            "previous_scene": {"name": "Empty", "path": ""},
            "active_scene": {"name": "Boot", "path": "Assets/Scenes/Boot.unity"},
            "failure_reason": "",
            "backend_id": "xuunity.light_unity_mcp",
            "_xuunity_lifecycle": {"idle_wait_after": {"bulk": list(range(50))}},
        }

        compact = server_bridge_payloads.compact_operation_payload(payload, "unity.scene.open")

        self.assertEqual("scene_opened", compact["outcome"])
        self.assertEqual("Boot", compact["active_scene"]["name"])
        self.assertEqual("Empty", compact["previous_scene"]["name"])
        self.assertNotIn("_xuunity_lifecycle", compact)
        self.assertNotIn("backend_id", compact)

    def test_compact_scene_snapshot_keeps_the_scene_content_and_counts_roots(self) -> None:
        payload = {
            "active_scene": {"name": "Boot", "path": "Assets/Scenes/Boot.unity", "is_dirty": False},
            "root_objects": [{"name": "Main Camera"}, {"name": "Directional Light"}],
            "backend_id": "xuunity.light_unity_mcp",
            "project_root": "/tmp/Project",
            "_xuunity_lifecycle": {"idle_wait_after": {"bulk": list(range(50))}},
        }

        compact = server_bridge_payloads.compact_operation_payload(payload, "unity.scene.snapshot")

        self.assertEqual("Boot", compact["active_scene"]["name"])
        self.assertEqual(2, compact["root_object_count"])
        self.assertEqual("Main Camera", compact["root_objects"][0]["name"])
        self.assertNotIn("_xuunity_lifecycle", compact)
        self.assertNotIn("project_root", compact)

    def test_compact_game_view_configure_keeps_the_resolved_view(self) -> None:
        payload = {
            "outcome": "game_view_configured",
            "game_view": {"width": 1170, "height": 2532, "label": "iPhone"},
            "backend_id": "xuunity.light_unity_mcp",
            "_xuunity_lifecycle": {"activation": {"noise": True}},
        }

        compact = server_bridge_payloads.compact_operation_payload(payload, "unity.game_view.configure")

        self.assertEqual("game_view_configured", compact["outcome"])
        self.assertEqual(1170, compact["game_view"]["width"])
        self.assertNotIn("_xuunity_lifecycle", compact)

    def test_a_snapshot_without_root_objects_does_not_invent_a_count(self) -> None:
        compact = server_bridge_payloads.compact_operation_payload(
            {"active_scene": {"name": "Boot"}, "root_objects": "corrupt"},
            "unity.scene.snapshot",
        )

        self.assertNotIn("root_object_count", compact)

    def test_the_full_scene_open_payload_stays_available_behind_the_opt_in(self) -> None:
        response = {
            "status": "ok",
            "payload_json": json.dumps({"outcome": "scene_opened", "opened": True}),
            "payload_type": "unity.scene.open",
            "_xuunity_lifecycle": {"operation": "unity.scene.open", "idle_wait_after": {"bulk": 1}},
        }

        compact_result = server_bridge_payloads.bridge_response_to_tool_result(
            dict(response),
            normalize_scenario_payload=lambda payload, statuses: payload,
            scenario_terminal_statuses=set(),
            include_full_payload=False,
        )
        compact_payload = compact_result["structuredContent"]
        self.assertEqual("compact_operation", compact_payload["payload_mode"])
        self.assertTrue(compact_payload["full_payload_available"])
        self.assertEqual({"includeFullPayload": True}, compact_payload["full_payload_tool_arguments"])
        self.assertNotIn("_xuunity_lifecycle", compact_payload)

        full_result = server_bridge_payloads.bridge_response_to_tool_result(
            dict(response),
            normalize_scenario_payload=lambda payload, statuses: payload,
            scenario_terminal_statuses=set(),
            include_full_payload=True,
        )
        full_payload = full_result["structuredContent"]
        self.assertIn("_xuunity_lifecycle", full_payload)
        self.assertEqual("scene_opened", full_payload["outcome"])

    def test_editor_open_attribution_survives_the_compact_scene_open_envelope(self) -> None:
        response = {
            "status": "ok",
            "payload_json": json.dumps({"outcome": "scene_opened"}),
            "payload_type": "unity.scene.open",
            "_xuunity_lifecycle": {
                "operation": "unity.scene.open",
                "activation": {
                    "editor_opened_by_this_call": True,
                    "editor_open_note": "opened for scene validation",
                },
            },
        }

        compact_result = server_bridge_payloads.bridge_response_to_tool_result(
            response,
            normalize_scenario_payload=lambda payload, statuses: payload,
            scenario_terminal_statuses=set(),
            include_full_payload=False,
        )

        compact_payload = compact_result["structuredContent"]
        self.assertTrue(compact_payload["editor_opened_by_this_call"])
        self.assertEqual("opened for scene validation", compact_payload["editor_open_note"])


class BlockedVersusFailedTests(unittest.TestCase):
    """A live-editor refusal is environmental; counting it as a compile failure misreads the whole rollout."""

    def test_a_live_editor_conflict_is_classified_as_blocked(self) -> None:
        payload = {
            "error": {
                "code": "editor_running_batch_conflict",
                "message": "An editor is open on this project.",
                "details": {"live_project_editor_pids": [4242]},
            }
        }

        self.assertEqual("editor_running_batch_conflict", run_multi_project.batch_error_code(payload))
        self.assertEqual([4242], run_multi_project.live_project_editor_pids_from_run(payload, {}))

    def test_pids_are_found_inside_the_batch_failure_summary(self) -> None:
        payload = {
            "error": {
                "details": {
                    "batch_failure_summary": {
                        "transport_outcome": "batch_prepare_blocked",
                        "live_project_editor_pids": [11, 22],
                    }
                }
            }
        }

        self.assertEqual([11, 22], run_multi_project.live_project_editor_pids_from_run(payload, {}))

    def test_a_genuine_failure_reports_no_live_editor(self) -> None:
        payload = {"error": {"code": "compile_player_scripts_failed", "details": {}}}

        self.assertEqual([], run_multi_project.live_project_editor_pids_from_run(payload, {}))
        self.assertNotEqual(
            run_multi_project.BLOCKED_BY_LIVE_EDITOR_VERDICT,
            run_multi_project.batch_error_code(payload),
        )


class UiTargetScopeSourceContractTests(unittest.TestCase):
    """UI reads must be able to leave the active scene, and must say so when a target is merely out of scope."""

    def test_all_loaded_scenes_is_a_declared_target_kind(self) -> None:
        models = read_source("Core/XUUnityLightMcpUiReadModels.cs")

        self.assertIn('TargetAllLoadedScenes = "all_loaded_scenes"', models)

    def test_every_ui_tool_offers_the_wider_scope(self) -> None:
        ui_tools = [
            name
            for name, tool in server_specs.TOOLS.items()
            if str(tool.get("bridgeOperation") or "").startswith("unity.ui.")
        ]
        self.assertTrue(ui_tools)

        for name in ui_tools:
            with self.subTest(tool=name):
                properties = server_specs.TOOLS[name]["inputSchema"]["properties"]
                self.assertIn("all_loaded_scenes", properties["targetKind"]["enum"])
                self.assertIn("sceneName", properties)
                self.assertIn("includeDontDestroyOnLoad", properties)

    def test_the_target_block_reports_whether_dont_destroy_on_load_was_searched(self) -> None:
        models = read_source("Core/XUUnityLightMcpUiReadModels.cs")

        for field in (
            "public bool dont_destroy_on_load_included;",
            "public List<string> searched_scenes",
            "public List<string> loaded_scenes",
        ):
            self.assertIn(field, models)

    def test_dont_destroy_on_load_status_never_contradicts_the_included_flag(self) -> None:
        """The DontDestroyOnLoad scene is discovered for `loaded_scenes` under every scope, but only *searched*
        under some. Reporting `included` while `dont_destroy_on_load_included` is false read as a contradiction
        on a live consumer-project run: `active_scene` said included=False / status=included."""

        models = read_source("Core/XUUnityLightMcpUiReadModels.cs")
        builder = read_source("Helpers/XUUnityLightMcpUiTreeBuilder.cs")

        self.assertIn('DontDestroyOnLoadOutOfScope = "out_of_scope_for_target_kind"', models)
        self.assertIn("ResolveDontDestroyOnLoadStatus(scope)", builder)
        self.assertIn("scope.DontDestroyOnLoadSearched", builder)

    def test_out_of_scope_is_distinct_from_not_found(self) -> None:
        builder = read_source("Helpers/XUUnityLightMcpUiTreeBuilder.cs")

        self.assertIn('"ui_target_out_of_scope"', builder)
        self.assertIn('"ui_target_not_found"', builder)
        self.assertIn("Retry with targetKind=all_loaded_scenes", builder)

    def test_a_zero_match_selector_probes_the_wider_scope_before_answering(self) -> None:
        """A live consumer-project run exposed the real gap: `unity.ui.query` with a selector returned
        `match_count: 0` and no diagnostic at all for a node sitting in an additively loaded scene —
        indistinguishable from "no such object", which is the exact failure the retro reported. Resolving
        the *root* out of scope was covered; resolving the *selector* out of scope was not."""

        query = read_source("Operations/XUUnityLightMcpUiQueryOperations.cs")

        self.assertIn("FindOwningScenesOutsideScope", query)
        self.assertIn("BuildZeroMatchDiagnostic", query)
        self.assertIn("IsWidestScope", query)
        self.assertIn('"ui_target_out_of_scope"', query)
        self.assertIn('"ui_node_not_found"', query)

    def test_the_wider_scope_probe_only_runs_on_a_zero_match(self) -> None:
        """The probe is a second full tree walk; it must stay on the diagnostic path, never the hot path."""

        query = read_source("Operations/XUUnityLightMcpUiQueryOperations.cs")

        self.assertIn("if (payload.match_count == 0 && payload.success)", query)
        self.assertIn("if (payload.target == null || IsWidestScope(payload.target))", query)

    def test_the_probe_is_skipped_when_the_scope_cannot_get_wider(self) -> None:
        """IsWidestScope required dont_destroy_on_load_included, which is unreachable in Edit Mode and after a
        failed probe, so every zero-match Edit Mode query paid a second full tree walk that could not find
        anything the first walk had not already seen."""

        query = read_source("Operations/XUUnityLightMcpUiQueryOperations.cs")

        self.assertIn("XUUnityLightMcpUiRead.SceneScopeAllLoadedScenes", query)
        for status in (
            "DontDestroyOnLoadEditModeUnavailable",
            "DontDestroyOnLoadProbeFailed",
            "DontDestroyOnLoadNotRequested",
        ):
            with self.subTest(status=status):
                self.assertIn(status, query)

    def test_out_of_scope_is_set_from_the_root_resolution_error_too(self) -> None:
        """payload.out_of_scope was assigned only inside the zero-match block, which builder errors skip by
        clearing payload.success first: the advertised boolean stayed false on the headline case."""

        query = read_source("Operations/XUUnityLightMcpUiQueryOperations.cs")

        self.assertIn(
            "payload.out_of_scope = HasOutOfScopeDiagnostic(payload.errors) "
            "|| HasOutOfScopeDiagnostic(payload.warnings)",
            query,
        )
        self.assertIn("payload.out_of_scope = payload.out_of_scope || zeroMatch.code", query)

    def test_a_zero_match_click_reports_the_scope_it_searched(self) -> None:
        """Click inspected builder errors only, and the root-canvas out-of-scope case is a warning, so the
        refusal was a bare "matched no node" with no scene sets - the retro's blocking symptom."""

        click = read_source("Ugui/XUUnityLightMcpUiClickOperation.cs")

        self.assertIn("foreach (var diagnostic in before.Warnings)", click)
        self.assertIn("XUUnityLightMcpUiTreeBuilder.DescribeSearchedScope(before.Target)", click)

    def test_a_zero_match_never_claims_more_than_the_probe_proved(self) -> None:
        """"no node in any loaded scene" is unfounded when the probe truncated or the scene selector matched
        several same-named scenes."""

        query = read_source("Operations/XUUnityLightMcpUiQueryOperations.cs")

        self.assertIn("ui_scope_probe_incomplete", query)
        self.assertIn("wide.Truncated || payload.target.scene_selector_ambiguous", query)

    def test_the_out_of_scope_advice_never_tells_a_root_bound_kind_to_drop_its_target(self) -> None:
        """For game_object_name/game_object_path, targetKind IS the root selector, so advising
        targetKind=all_loaded_scenes discards targetValue and returns an unrelated all-canvases tree. The probe
        itself must still widen, which is why the fix is in the advice rather than in the probe's options."""

        query = read_source("Operations/XUUnityLightMcpUiQueryOperations.cs")

        self.assertIn("static string ResolveOutOfScopeRetry", query)
        self.assertIn("keeping targetKind=", query)
        self.assertIn("TargetKind = XUUnityLightMcpUiRead.TargetAllLoadedScenes,", query)

    def test_a_duplicate_scene_name_is_named_rather_than_silently_widening(self) -> None:
        builder = read_source("Helpers/XUUnityLightMcpUiTreeBuilder.cs")
        models = read_source("Core/XUUnityLightMcpUiReadModels.cs")

        self.assertIn("ui_scene_selector_ambiguous", builder)
        self.assertIn("RequestedSceneAmbiguous = scope.Searched.Count > 1", builder)
        self.assertIn("public bool scene_selector_ambiguous;", models)

    def test_the_target_never_names_a_scene_it_did_not_search(self) -> None:
        builder = read_source("Helpers/XUUnityLightMcpUiTreeBuilder.cs")

        self.assertNotIn("scope.Searched.Count > 0 ? scope.Searched[0] : SceneManager.GetActiveScene()", builder)
        self.assertIn("if (scope.Searched.Count == 1 && scope.Searched[0].IsValid())", builder)

    def test_out_of_scope_is_a_first_class_payload_field(self) -> None:
        models = read_source("Core/XUUnityLightMcpUiReadModels.cs")

        self.assertIn("public bool out_of_scope;", models)

    def test_the_click_target_is_not_re_resolved_by_name_lookup(self) -> None:
        """GameObject.Find cannot address every additive/DontDestroyOnLoad object the tree can now reach."""

        click = read_source("Ugui/XUUnityLightMcpUiClickOperation.cs")

        self.assertNotIn("GameObject.Find(", click)
        self.assertIn("before.ResolveTransform(node)", click)

    def test_the_tree_builder_keeps_transforms_in_lockstep_with_nodes(self) -> None:
        builder = read_source("Helpers/XUUnityLightMcpUiTreeBuilder.cs")

        self.assertIn("result.Nodes.Add(node);", builder)
        self.assertIn("result.NodeTransforms.Add(transform);", builder)


class PlayModeRefusalSourceContractTests(unittest.TestCase):
    """"Editor is busy" hid the one thing the operator needed to know: it is in Play Mode."""

    def test_the_guard_names_play_mode_and_both_valid_next_actions(self) -> None:
        guard = read_source("Helpers/XUUnityLightMcpEditorBusyGuard.cs")

        self.assertIn('EditorInPlayModeCode = "editor_in_play_mode"', guard)
        self.assertIn("unity.playmode.set action=stop", guard)
        self.assertIn("closed-project batch lane", guard)

    def test_no_operation_still_raises_the_bare_busy_string(self) -> None:
        offenders = []
        for source in sorted(PACKAGE_EDITOR_ROOT.rglob("*.cs")):
            if source.name == "XUUnityLightMcpEditorBusyGuard.cs":
                continue
            if re.search(r'"Unity editor is busy', source.read_text(encoding="utf-8")):
                offenders.append(str(source.relative_to(REPO_ROOT)))

        self.assertEqual([], offenders, "route editor-busy refusals through XUUnityLightMcpEditorBusyGuard")

    def test_the_refusing_operations_map_the_typed_code_onto_the_response(self) -> None:
        for relative in (
            "Operations/XUUnityLightMcpCompilePlayerScriptsOperation.cs",
            "Operations/XUUnityLightMcpCompileMatrixOperation.cs",
        ):
            with self.subTest(source=relative):
                self.assertIn("XUUnityLightMcpEditorBusyGuard.ResolveErrorCode", read_source(relative))


class ScreenshotBudgetSourceContractTests(unittest.TestCase):
    """One includeImage call returned 184,659 characters and wasted the whole call."""

    def test_the_budget_is_checked_before_base64_is_built(self) -> None:
        utility = read_source("Helpers/XUUnityLightMcpGameViewUtility.cs")

        encode_at = utility.index("EncodeToPNG();\n                    imageBytes")
        base64_at = utility.index("Convert.ToBase64String(inlineBytes)")
        self.assertLess(encode_at, base64_at, "size must be known before the base64 string is allocated")
        self.assertIn("imageBytes <= budget", utility)

    def test_the_payload_explains_an_omitted_image(self) -> None:
        models = read_source("Core/XUUnityLightMcpGameViewProjectResolveModels.cs")

        self.assertIn('ImageOmittedPayloadBudget = "payload_budget"', models)
        self.assertIn("public string image_omitted_reason", models)
        self.assertIn("public int image_budget_bytes;", models)

    def test_the_tool_documents_the_file_path_first_path(self) -> None:
        tool = server_specs.TOOLS["unity_game_view_screenshot"]

        self.assertIn("file_path", tool["description"])
        self.assertIn("imageBudgetBytes", tool["inputSchema"]["properties"])


if __name__ == "__main__":
    unittest.main()
