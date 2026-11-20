from __future__ import annotations

import re
from typing import Any

CONSOLE_ITEM_DEFAULT_MAX_BYTES = 2048
CONSOLE_ITEM_TRUNCATION_MARKER = " [truncated_by_item_cap]"
CONSOLE_REDACTION_SCAN_MARGIN_CHARS = 1024
CONSOLE_ITEM_CAP_RECOVERY_HINT = "Pass maxItemBytes=-1 for the full line, or a larger maxItemBytes."
CONSOLE_REDACTION_NOTE = (
    "Token-like values in the returned log lines were replaced with [REDACTED]. "
    "The log file on disk is unchanged."
)
REDACTED = "[REDACTED]"

_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}")
_AUTH_SCHEME_PATTERN = re.compile(r"(?i)\b(Bearer|Basic)(\s+)([A-Za-z0-9._~+/=-]{8,})")
_KEYED_VALUE_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])(?P<key>[A-Za-z0-9_.-]{0,48}?"
    r"(?:token|secret|passw(?:or)?d|api[_-]?key|authorization|credential|cookie|private[_-]?key)"
    r"[A-Za-z0-9_.-]{0,48})"
    r"(?P<sep>[\"']?\s*[:=]\s*[\"']?)"
    r"(?P<value>[^\s\"',;&<>{}\[\]()]+)"
)
_ALWAYS_SECRET_KEY_PATTERN = re.compile(r"(?i)secret|passw(?:or)?d|private[_-]?key")
_ITEM_TEXT_FIELDS = ("message", "stack_trace")
_ITEM_LINE_LIST_FIELDS = ("context_before", "context_after")


def _keyed_value_is_secret(key: str, value: str) -> bool:
    if _ALWAYS_SECRET_KEY_PATTERN.search(key):
        return len(value) >= 4
    if len(value) < 8:
        return False
    if any(char.isdigit() for char in value):
        return True
    return len(value) >= 20 and any(not (char.isalpha() or char == ".") for char in value)


def redact_console_secrets(text: str, scan_chars: int = -1) -> tuple[str, int]:
    if not text:
        return text, 0
    if 0 <= scan_chars < len(text):
        head, count = redact_console_secrets(text[:scan_chars])
        return head + text[scan_chars:], count
    count = 0

    def replace_jwt(_match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return REDACTED

    def replace_scheme(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{match.group(1)}{match.group(2)}{REDACTED}"

    def replace_keyed(match: re.Match[str]) -> str:
        nonlocal count
        if not _keyed_value_is_secret(match.group("key"), match.group("value")):
            return match.group(0)
        count += 1
        return f"{match.group('key')}{match.group('sep')}{REDACTED}"

    redacted = _JWT_PATTERN.sub(replace_jwt, text)
    redacted = _AUTH_SCHEME_PATTERN.sub(replace_scheme, redacted)
    redacted = _KEYED_VALUE_PATTERN.sub(replace_keyed, redacted)
    return redacted, count


def resolve_console_item_byte_cap(requested: Any) -> int:
    if requested is None or isinstance(requested, bool):
        return CONSOLE_ITEM_DEFAULT_MAX_BYTES
    try:
        value = int(requested)
    except (TypeError, ValueError):
        return CONSOLE_ITEM_DEFAULT_MAX_BYTES
    if value < 0:
        return -1
    return CONSOLE_ITEM_DEFAULT_MAX_BYTES if value == 0 else value


def _cap_text(text: str, cap: int) -> tuple[str, bool]:
    if cap < 0:
        return text, False
    encoded = text.encode("utf-8")
    if len(encoded) <= cap:
        return text, False
    return encoded[:cap].decode("utf-8", errors="ignore") + CONSOLE_ITEM_TRUNCATION_MARKER, True


def _payload_budget_is_unbounded(max_payload_bytes: Any) -> bool:
    return isinstance(max_payload_bytes, int) and not isinstance(max_payload_bytes, bool) and max_payload_bytes < 0


def finalize_console_items(
    payload: dict[str, Any],
    max_item_bytes: Any = None,
    max_payload_bytes: Any = None,
) -> dict[str, Any]:
    annotated = dict(payload or {})
    if "max_item_bytes" in annotated:
        return annotated
    if max_item_bytes is None and _payload_budget_is_unbounded(max_payload_bytes):
        max_item_bytes = -1
    cap = resolve_console_item_byte_cap(max_item_bytes)
    scan_chars = -1 if cap < 0 else cap + CONSOLE_REDACTION_SCAN_MARGIN_CHARS
    redacted_count = 0
    capped_count = 0
    items: list[Any] = []
    for raw_item in annotated.get("items") or []:
        if not isinstance(raw_item, dict):
            items.append(raw_item)
            continue
        item = dict(raw_item)
        for field in _ITEM_TEXT_FIELDS:
            value = item.get(field)
            if isinstance(value, str) and value:
                item[field], count = redact_console_secrets(value, scan_chars if field == "message" else -1)
                redacted_count += count
        for field in _ITEM_LINE_LIST_FIELDS:
            lines = item.get(field)
            if isinstance(lines, list):
                cleaned = []
                for line in lines:
                    text, count = redact_console_secrets(str(line), scan_chars)
                    redacted_count += count
                    cleaned.append(_cap_text(text, cap)[0])
                item[field] = cleaned
        message = item.get("message")
        if isinstance(message, str):
            original_bytes = len(message.encode("utf-8"))
            item["message"], was_capped = _cap_text(message, cap)
            if was_capped:
                item["message_bytes_before_cap"] = original_bytes
                capped_count += 1
        items.append(item)
    if "items" in annotated:
        annotated["items"] = items
    annotated["max_item_bytes"] = cap
    annotated["items_truncated_for_item_cap"] = capped_count
    if capped_count:
        annotated["item_cap_recovery_hint"] = CONSOLE_ITEM_CAP_RECOVERY_HINT
    annotated["redacted_secret_count"] = redacted_count
    if redacted_count:
        annotated["redaction_note"] = CONSOLE_REDACTION_NOTE
    return annotated
