from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server_bridge_paths import request_journal_dir

TEST_RUN_OPERATIONS = frozenset({"unity.tests.run_editmode", "unity.tests.run_playmode"})
TEST_FILTER_ARGUMENTS = ("testNames", "groupNames", "categoryNames", "assemblyNames")
SUITE_TIMEOUT_HEADROOM = 1.5
RECENT_COMPLETION_SCAN_LIMIT = 400
RECENT_RUN_SAMPLE_LIMIT = 10


def is_unfiltered_test_run(operation: str, arguments: dict[str, Any]) -> bool:
    if operation not in TEST_RUN_OPERATIONS:
        return False
    for key in TEST_FILTER_ARGUMENTS:
        value = arguments.get(key)
        if isinstance(value, list) and any(str(item).strip() for item in value):
            return False
        if isinstance(value, str) and value.strip():
            return False
    return True


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def recent_test_run_durations_ms(project_root: Path, operation: str) -> list[int]:
    journal = request_journal_dir(project_root)
    try:
        names = sorted(
            (entry.name for entry in journal.iterdir() if entry.name.endswith("_request_completed.json")),
            reverse=True,
        )
    except OSError:
        return []

    durations: list[int] = []
    for name in names[:RECENT_COMPLETION_SCAN_LIMIT]:
        try:
            event = json.loads((journal / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(event, dict) or str(event.get("operation") or "") != operation:
            continue
        started = _parse_utc(event.get("started_at_utc"))
        completed = _parse_utc(event.get("completed_at_utc"))
        if started is None or completed is None or completed < started:
            continue
        durations.append(int((completed - started).total_seconds() * 1000))
        if len(durations) >= RECENT_RUN_SAMPLE_LIMIT:
            break
    return durations


def suite_aware_default_timeout_ms(project_root: Path, operation: str, declared_default_ms: int) -> tuple[int, str]:
    durations = recent_test_run_durations_ms(project_root, operation)
    if not durations:
        return declared_default_ms, "declared_default"
    suggested = int(math.ceil(max(durations) * SUITE_TIMEOUT_HEADROOM / 1000.0)) * 1000
    if suggested <= declared_default_ms:
        return declared_default_ms, "declared_default"
    return suggested, "recent_suite_duration"
