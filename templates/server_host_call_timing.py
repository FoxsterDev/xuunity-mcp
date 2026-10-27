"""Opt-in host timings; no Unity or client-clock attribution."""
from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator, TypeVar


STAGES = (
    "context_discovery", "activation", "idle_before",
    "dispatch_unity_wait", "idle_after", "serialization",
)
_ACTIVE: ContextVar[HostCallTiming | None] = ContextVar("xuunity_host_call_timing", default=None)
_T = TypeVar("_T")


class HostCallTiming:
    def __init__(self, scope: str) -> None:
        self.scope = scope
        self.started_ns = time.monotonic_ns()
        self.request_id: Any = None
        self.tool_name = ""
        self.durations = {name: 0 for name in STAGES}
        self.counts = {name: 0 for name in STAGES}
        self.failures = {name: 0 for name in STAGES}
        self.stack: list[list[Any]] = []

    @contextmanager
    def measure(self, stage: str) -> Iterator[None]:
        frame = [stage, time.monotonic_ns(), 0]
        self.stack.append(frame)
        self.counts[stage] += 1
        try:
            yield
        except BaseException:
            self.failures[stage] += 1
            raise
        finally:
            elapsed = time.monotonic_ns() - frame[1]
            self.stack.pop()
            self.durations[stage] += elapsed - frame[2]
            if self.stack:
                self.stack[-1][2] += elapsed

    def snapshot(self, boundary: str) -> dict[str, Any]:
        total_ns = time.monotonic_ns() - self.started_ns
        measured_ns = sum(self.durations.values())
        residual_ns = total_ns - measured_ns
        active_stages = {frame[0] for frame in self.stack}
        return {
            "schema_version": 1,
            "scope": self.scope,
            "boundary": boundary,
            "clock": "monotonic_ns",
            "total_seconds": total_ns / 1_000_000_000,
            "measured_stage_total_seconds": measured_ns / 1_000_000_000,
            "unattributed_seconds": residual_ns / 1_000_000_000,
            "accounting_valid": residual_ns >= 0,
            "stages": {
                name: {
                    "status": "partial" if name in active_stages else "measured" if self.counts[name] else "unmeasured",
                    "duration_seconds": self.durations[name] / 1_000_000_000 if self.counts[name] and name not in active_stages else None,
                    "invocation_count": self.counts[name],
                    "failure_count": self.failures[name],
                }
                for name in STAGES
            },
            "excludes": ["launcher_startup", "client_latency", "diagnostic_receipt_emission"],
        }


@contextmanager
def host_call_timing_scope(scope: str) -> Iterator[HostCallTiming | None]:
    existing = _ACTIVE.get()
    if existing is not None or os.environ.get("XUUNITY_HOST_CALL_TIMING") != "1":
        yield existing
        return
    timing = HostCallTiming(scope)
    token = _ACTIVE.set(timing)
    try:
        yield timing
    finally:
        _ACTIVE.reset(token)


@contextmanager
def measure_host_stage(stage: str) -> Iterator[None]:
    timing = _ACTIVE.get()
    if timing is None:
        yield
    else:
        with timing.measure(stage):
            yield


def timed_host_call(stage: str, callback: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
    with measure_host_stage(stage):
        return callback(*args, **kwargs)


def emit_host_call_timing_receipt(boundary: str, outcome: str = "completed") -> None:
    timing = _ACTIVE.get()
    if timing is None or not timing.tool_name:
        return
    # Diagnostic failure must not change the operation or hide an I/O exception.
    try:
        receipt = timing.snapshot(boundary)
        receipt.update({"event": "xuunity_host_call_timing", "outcome": outcome,
                        "request_id": timing.request_id, "tool_name": timing.tool_name})
        sys.stderr.write(json.dumps(receipt, ensure_ascii=True, separators=(",", ":")) + "\n")
        sys.stderr.flush()
    except Exception:
        pass
