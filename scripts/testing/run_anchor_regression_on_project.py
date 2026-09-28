#!/usr/bin/env python3
"""Anchor-evidence regression suite against a real Unity project and its real Editor.log.

The unit suite proves the anchor logic on synthetic logs. This one proves it where the defects were found:
a multi-megabyte Editor.log that accumulates across sessions, a live editor whose stamped log path is the
platform log rather than the project-local one, and a post-anchor scope large enough to trip the max_chars
truncation path that reopened the fabricated-match defect.

Every case reports PASS/FAIL with the evidence it checked, and reported line numbers are verified against the
log file itself rather than trusted from the payload.

Usage:
    python3 scripts/testing/run_anchor_regression_on_project.py --project-root <unity project>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPO_ROOT / "xuunity_light_unity_mcp.sh"
TEMPLATES = REPO_ROOT / "templates"
if str(TEMPLATES) not in sys.path:
    sys.path.insert(0, str(TEMPLATES))

import server_bridge_paths  # noqa: E402
import server_health  # noqa: E402


class Outcome:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def check(self, label: str, condition: bool, evidence: str) -> bool:
        if condition:
            self.passed += 1
            print(f"  PASS  {label}\n        {evidence}")
        else:
            self.failed += 1
            print(f"  FAIL  {label}\n        {evidence}")
        return condition

    def skip(self, label: str, why: str) -> None:
        self.skipped += 1
        print(f"  SKIP  {label}\n        {why}")


def run_wrapper(args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        [str(WRAPPER), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        cwd=str(REPO_ROOT),
    )
    body = ""
    for line in completed.stdout.splitlines():
        if line.startswith("{"):
            body = line
    if not body:
        raise RuntimeError(f"no JSON envelope from {' '.join(args)}\n{completed.stdout[-2000:]}")
    envelope = json.loads(body)
    payload_json = envelope.get("payload_json")
    return json.loads(payload_json) if isinstance(payload_json, str) and payload_json else envelope


def read_bridge_state(project_root: Path) -> dict[str, Any]:
    path = server_bridge_paths.bridge_state_path(project_root)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def log_line(log_path: Path, number: int) -> str:
    with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for index, line in enumerate(handle, start=1):
            if index == number:
                return line.rstrip("\n")
    return ""


def case_mismatch_is_refused(outcome: Outcome, project_root: Path, state: dict[str, Any]) -> None:
    print("\n[1] An offset stamped against another Editor.log must be refused, not applied")
    stamped = str(state.get("editor_log_path") or "")
    if not stamped:
        outcome.skip("anchor_log_mismatch", "bridge_state carries no editor_log_path")
        return

    payload = run_wrapper(
        [
            "request-console-grep",
            "--project-root", str(project_root),
            "--pattern", "Unity Editor version",
            "--since", "playmode_start",
            "--limit", "3",
        ]
    )
    anchor = payload.get("since_anchor", {})
    searched = str(payload.get("editor_log_path") or "")
    if server_health._same_path(Path(stamped), Path(searched)):
        outcome.skip(
            "anchor_log_mismatch",
            f"host resolved the same log the editor stamped ({searched}); nothing to mismatch",
        )
        return

    outcome.check(
        "anchor_log_mismatch refuses a cross-log offset",
        anchor.get("resolved") == "anchor_log_mismatch" and not anchor.get("anchored"),
        f"resolved={anchor.get('resolved')} anchored={anchor.get('anchored')}",
    )
    outcome.check(
        "the refusal names both logs",
        bool(anchor.get("stamped_editor_log_path")) and bool(anchor.get("searched_editor_log_path")),
        f"stamped={anchor.get('stamped_editor_log_path')} searched={anchor.get('searched_editor_log_path')}",
    )
    outcome.check(
        "a refused anchor never claims session scope",
        payload.get("result_trust_class") == "editor_log_spans_multiple_sessions"
        and bool(payload.get("stale_match_caveat")),
        f"trust={payload.get('result_trust_class')} caveat={bool(payload.get('stale_match_caveat'))}",
    )


def resolve_stamping_log(state: dict[str, Any]) -> tuple[Path | None, str]:
    """The log the stamping editor actually writes, which is not always the path it reports.

    Unity rotates `Editor.log` to `Editor-prev.log` when a second editor starts; the first editor keeps writing
    the renamed file while `Application.consoleLogPath` still returns the static path. The anchor resolver refuses
    that case as `anchor_log_rotated`, so the log to test against is whichever candidate it accepts.
    """

    stamped = str(state.get("editor_log_path") or "")
    if not stamped:
        return None, "bridge_state carries no editor_log_path"

    reasons: list[str] = []
    candidates = [Path(stamped)]
    rotated = Path(stamped).with_name(Path(stamped).stem + "-prev" + Path(stamped).suffix)
    if rotated.is_file():
        candidates.append(rotated)

    for candidate in candidates:
        # Probe exactly as a caller would: the stamped path travels with the state, so a candidate that differs
        # from it must still satisfy the mismatch check. Overriding it here would prove nothing.
        anchor = server_health.resolve_editor_log_since_anchor(
            candidate,
            since="playmode_start",
            bridge_state=state,
        )
        if anchor.get("anchored"):
            return candidate, ""
        reasons.append(f"{candidate.name}: {anchor.get('resolved')}")
    return None, (
        "no candidate log anchors cleanly ("
        + "; ".join(reasons)
        + "). On a multi-editor host the stamped path is rotated and the log the editor writes fails the path "
        "check, so anchoring is refused in both directions until the resolver forward-resolves a rotated stamp."
    )


def case_rotated_path_is_refused(outcome: Outcome, state: dict[str, Any]) -> None:
    print("\n[2] A rotated log path must be refused even though the editor is alive")
    stamped = str(state.get("editor_log_path") or "")
    if not stamped:
        outcome.skip("anchor_log_rotated", "bridge_state carries no editor_log_path")
        return

    anchor = server_health.resolve_editor_log_since_anchor(
        Path(stamped),
        since="playmode_start",
        bridge_state=state,
    )
    if anchor.get("anchored"):
        outcome.skip(
            "anchor_log_rotated",
            f"{stamped} is still the log this editor writes; open a second editor to reproduce the rotation",
        )
        return

    outcome.check(
        "a path whose file predates its own stamp is refused",
        anchor.get("resolved") == "anchor_log_rotated",
        f"resolved={anchor.get('resolved')} stamped_at={anchor.get('stamped_at_utc')} "
        f"log_mtime={anchor.get('searched_editor_log_mtime_utc')}",
    )
    outcome.check(
        "the refusal names the remediation",
        "Editor-prev.log" in str(anchor.get("recommended_next_action") or ""),
        "recommended_next_action points at the log the editor actually writes",
    )


def case_real_anchor_and_truncation(outcome: Outcome, project_root: Path, state: dict[str, Any]) -> None:
    print("\n[3] A real anchor on the log the editor writes, including the max_chars truncation path")
    resolved, why = resolve_stamping_log(state)
    offset = int(state.get("editor_log_offset_at_playmode_start") or 0)
    if resolved is None or offset <= 0:
        outcome.skip("real anchor", why or "no playmode_start offset recorded yet; enter Play Mode first")
        return

    stamped = str(resolved)
    log_path = resolved
    size = log_path.stat().st_size
    scope_bytes = max(0, size - offset)
    # An omitted budget now searches the whole anchored scope, so the truncation contract is probed with an
    # explicit small budget and the auto-extension contract with no budget at all.
    budget_args = ["--max-search-chars", "65536"] if scope_bytes > 65536 else []
    payload = run_wrapper(
        [
            "request-console-grep",
            "--project-root", str(project_root),
            "--editor-log-path", stamped,
            "--pattern", "e",
            "--since", "playmode_start",
            "--limit", "5",
            *budget_args,
        ]
    )
    anchor = payload.get("since_anchor", {})

    outcome.check(
        "the anchor resolves against the log the editor stamped",
        anchor.get("resolved") == "playmode_start" and anchor.get("anchored") is True,
        f"resolved={anchor.get('resolved')} offset={anchor.get('start_offset_bytes')} scope_bytes={scope_bytes}",
    )
    truncated = bool(anchor.get("scope_truncated"))
    expected_trust = (
        "session_scoped_editor_log_partial_scope" if truncated else "session_scoped_editor_log"
    )
    outcome.check(
        "an anchored result is labelled with its full or partial session scope",
        payload.get("result_trust_class") == expected_trust and not payload.get("stale_match_caveat"),
        f"trust={payload.get('result_trust_class')} truncated={truncated}",
    )

    if not truncated:
        outcome.skip(
            "truncation boundary",
            f"scope is {scope_bytes} bytes, under the {payload.get('searched_window_chars')} char budget",
        )
    else:
        outcome.check(
            "an anchored grep keeps the anchor-adjacent head",
            payload.get("search_window_direction") == "anchor_adjacent_head",
            f"direction={payload.get('search_window_direction')}",
        )
        outcome.check(
            "an anchor-adjacent window preserves absolute line numbers",
            payload.get("line_numbering_basis") == "editor_log_absolute"
            and int(payload.get("searched_from_line") or 0) > 0
            and "anchor_line" not in anchor,
            f"basis={payload.get('line_numbering_basis')} from_line={payload.get('searched_from_line')} "
            f"anchor_line={anchor.get('anchor_line')}",
        )
        first = payload.get("items") or []
        if first:
            text = str(first[0].get("message") or "")
            outcome.check(
                "the first returned line is a whole line of the real log",
                text in _scope_lines(log_path, offset),
                f"first item is a complete log line ({len(text)} chars)",
            )

        absent = run_wrapper(
            [
                "request-console-grep",
                "--project-root", str(project_root),
                "--editor-log-path", stamped,
                "--pattern", "__XUUNITY_MCP_ANCHORED_SCOPE_ABSENCE_PROBE_9F1834__",
                "--since", "playmode_start",
                "--limit", "3",
                *budget_args,
            ]
        )
        outcome.check(
            "a partial zero-match is inconclusive rather than negative",
            absent.get("match_count") == 0
            and absent.get("search_verdict") == "inconclusive"
            and absent.get("scope_truncated") is True,
            f"matches={absent.get('match_count')} verdict={absent.get('search_verdict')} "
            f"reason={absent.get('search_verdict_reason')}",
        )
        outcome.check(
            "the inconclusive result names recovery",
            bool(absent.get("recommended_next_action")),
            f"recommended_next_action={absent.get('recommended_next_action')}",
        )

    if 500000 < scope_bytes <= 10_000_000:
        extended = run_wrapper(
            [
                "request-console-grep",
                "--project-root", str(project_root),
                "--editor-log-path", stamped,
                "--pattern", "__XUUNITY_MCP_ANCHORED_SCOPE_ABSENCE_PROBE_9F1834__",
                "--since", "playmode_start",
                "--limit", "3",
            ]
        )
        outcome.check(
            "an omitted budget searches the whole anchored scope and turns the zero-match into not_matched",
            extended.get("search_window_auto_extended") is True
            and extended.get("scope_truncated") is False
            and extended.get("search_verdict") == "not_matched",
            f"auto_extended={extended.get('search_window_auto_extended')} truncated={extended.get('scope_truncated')} "
            f"verdict={extended.get('search_verdict')} searched={extended.get('searched_window_chars')}",
        )
    else:
        outcome.skip(
            "auto-extension",
            f"scope is {scope_bytes} bytes; an omitted budget auto-extends only above 500000 bytes and up to 10000000",
        )


def _scope_lines(log_path: Path, offset: int) -> set[str]:
    with log_path.open("rb") as handle:
        handle.seek(offset)
        raw = handle.read()
    return {line.rstrip("\r") for line in raw.decode("utf-8", errors="ignore").split("\n")}


def case_tail_line_numbers_are_real(
    outcome: Outcome,
    project_root: Path,
    state: dict[str, Any],
    request_id: str = "",
) -> None:
    print("\n[5] Tail line numbers must match the real log, blank lines included")
    resolved, why = resolve_stamping_log(state)
    if resolved is None:
        outcome.skip("tail numbering", why)
        return

    stamped = str(resolved)
    log_path = resolved
    payload: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    # Absolute numbering is what needs checking here, and only a scope that is both non-empty and inside the
    # max_chars budget reports it: a playmode_start scope on a long session truncates to relative numbering, and
    # a bridge_generation anchor right after a reload sits at EOF. A recent request id gives a small live scope.
    candidates = ([("request_id", request_id)] if request_id else []) + [
        ("bridge_generation", ""),
        ("playmode_start", ""),
    ]
    for since, anchor_request_id in candidates:
        command = [
            "request-console-tail",
            "--project-root", str(project_root),
            "--editor-log-path", stamped,
            "--since", since,
            "--limit", "8",
        ]
        if anchor_request_id:
            command += ["--since-request-id", anchor_request_id]
        payload = run_wrapper(command)
        anchor = payload.get("since_anchor", {})
        if not anchor.get("anchored"):
            continue
        if payload.get("line_numbering_basis") != "editor_log_absolute":
            continue
        items = payload.get("items") or []
        if items:
            print(f"        anchored on {since}, {len(items)} items, absolute basis")
            break

    if not items:
        outcome.skip(
            "tail numbering",
            "no anchor produced a non-empty scope under absolute numbering "
            f"(last: {payload.get('line_numbering_basis')}, {payload.get('since_anchor', {}).get('resolved')})",
        )
        return

    mismatches = []
    for item in items:
        number = int(item.get("line") or 0)
        expected = log_line(log_path, number)
        if expected != str(item.get("message") or ""):
            mismatches.append((number, expected, item.get("message")))

    outcome.check(
        "every reported line number resolves to that exact line in the file",
        not mismatches,
        f"verified {len(items)} items against the log; mismatches={len(mismatches)}"
        + (f" first={mismatches[0]}" if mismatches else ""),
    )


def case_request_id_carries_identity(outcome: Outcome, project_root: Path) -> str:
    print("\n[4] A request_id anchor must carry its own log identity")
    journal_dir = project_root / "Library" / "XUUnityLightMcp" / "journal" / "requests"

    # Journal events already on disk were written by whichever assembly was loaded at the time, so on a project
    # that just switched packages the newest one predates the code under test. Issue one cheap bridge request so
    # the running assembly writes a fresh event, then read that.
    before = set(journal_dir.glob("*_request_started.json")) if journal_dir.is_dir() else set()
    run_wrapper(["request-playmode-state", "--project-root", str(project_root)])
    events = sorted(journal_dir.glob("*_request_started.json")) if journal_dir.is_dir() else []
    fresh = [path for path in events if path not in before]
    if not fresh:
        outcome.skip("request_id identity", "the bridge wrote no new request_started event")
        return ""

    newest = json.loads(sorted(fresh)[-1].read_text(encoding="utf-8"))
    print(f"        fresh event from bridge_generation={newest.get('bridge_generation')}")
    outcome.check(
        "the editor stamps editor_log_path beside editor_log_offset_bytes",
        bool(str(newest.get("editor_log_path") or "")) and int(newest.get("editor_log_offset_bytes") or 0) > 0,
        f"offset={newest.get('editor_log_offset_bytes')} path={newest.get('editor_log_path')}",
    )

    request_id = str(newest.get("request_id") or "")
    if not request_id:
        outcome.skip("request_id anchor", "newest request_started event carries no request_id")
        return ""

    resolved, why = resolve_stamping_log(read_bridge_state(project_root))
    if resolved is None:
        outcome.skip("request_id anchor", why)
        return request_id

    payload = run_wrapper(
        [
            "request-console-grep",
            "--project-root", str(project_root),
            "--editor-log-path", str(resolved),
            "--pattern", "e",
            "--since", "request_id",
            "--since-request-id", request_id,
            "--limit", "3",
        ]
    )
    anchor = payload.get("since_anchor", {})
    outcome.check(
        "the anchor resolves from the journal offset",
        anchor.get("resolved") == "request_id" and anchor.get("anchored") is True,
        f"resolved={anchor.get('resolved')} offset={anchor.get('start_offset_bytes')}",
    )
    return request_id


def case_live_state_is_trusted(outcome: Outcome, project_root: Path) -> None:
    print("\n[5] A live editor's state must still anchor (the dead-session guard must not over-refuse)")
    sys.path.insert(0, str(TEMPLATES))
    import server_batch_orchestrator as orchestrator

    _, _, is_live = orchestrator.editor_log_anchor_state(project_root, "playmode_start")
    outcome.check(
        "a running editor's bridge_state is classified live",
        is_live is True,
        f"bridge_state_is_live={is_live}",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    state = read_bridge_state(project_root)

    print(f"anchor regression suite against {project_root}")
    print(f"editor_pid={state.get('editor_pid')} unity={state.get('unity_version')} "
          f"bridge_generation={state.get('bridge_generation')}")

    outcome = Outcome()
    case_mismatch_is_refused(outcome, project_root, state)
    case_rotated_path_is_refused(outcome, state)
    case_real_anchor_and_truncation(outcome, project_root, state)
    fresh_request_id = case_request_id_carries_identity(outcome, project_root)
    case_tail_line_numbers_are_real(outcome, project_root, state, fresh_request_id)
    case_live_state_is_trusted(outcome, project_root)

    print(f"\npassed={outcome.passed} failed={outcome.failed} skipped={outcome.skipped}")
    return 1 if outcome.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
