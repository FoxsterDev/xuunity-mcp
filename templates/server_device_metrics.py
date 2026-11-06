from __future__ import annotations

import re
import statistics
from typing import Any, Iterable

INT64_MAX = 9223372036854775807
GAP_THRESHOLDS_MS = (33, 50, 100, 250, 500)
TOP_GAP_COUNT = 10


SURFACE_LAYER_BASES = frozenset({"surfaceview_blast", "surfaceview"})
NON_PRESENTING_LAYER_MARKERS = ("Background for", "ActivityRecordInputSink", "InputSink", "ActivityRecord{", "Splash Screen")


def _owns_layer(layer: str, package: str) -> bool:
    return re.search(rf"(?<![\w.]){re.escape(package)}(?=[/#\])\s]|$)", layer) is not None


def select_app_layer(layer_list: str, package: str) -> tuple[str, str]:
    layers = [line.strip() for line in layer_list.splitlines() if line.strip()]
    owned = [
        layer
        for layer in layers
        if _owns_layer(layer, package) and not any(marker in layer for marker in NON_PRESENTING_LAYER_MARKERS)
    ]
    ranked = (
        ("surfaceview_blast", lambda layer: layer.startswith("SurfaceView[") and "(BLAST)" in layer),
        ("surfaceview", lambda layer: layer.startswith("SurfaceView[") or layer.startswith("SurfaceView -")),
        ("blast", lambda layer: "(BLAST)" in layer),
        ("activity", lambda layer: "/" in layer),
    )
    for basis, accepts in ranked:
        for layer in owned:
            if accepts(layer):
                return layer, basis
    return "", "no_layer_for_package"


def parse_latency(output: str) -> tuple[int, list[int]]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return 0, []
    try:
        refresh_ns = int(lines[0].split()[0])
    except (ValueError, IndexError):
        refresh_ns = 0
    presents: list[int] = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            desired, actual, ready = (int(part) for part in parts[:3])
        except ValueError:
            continue
        value = actual if 0 < actual < INT64_MAX else desired
        if 0 < value < INT64_MAX:
            presents.append(value)
    return refresh_ns, presents


class PresentAccumulator:
    def __init__(self) -> None:
        self.presents: set[int] = set()
        self.sample_count = 0
        self.sample_gaps: list[dict[str, float]] = []
        self._last_max: int | None = None

    def add_sample(self, presents: list[int]) -> None:
        self.sample_count += 1
        if not presents:
            return
        first, last = min(presents), max(presents)
        if self._last_max is not None and first > self._last_max and len(presents) >= 127:
            self.sample_gaps.append({"from_s": self._last_max / 1e9, "to_s": first / 1e9})
        self._last_max = max(last, self._last_max or last)
        self.presents.update(presents)

    def sorted_presents(self) -> list[int]:
        return sorted(self.presents)


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, int(round(fraction * (len(sorted_values) - 1)))))
    return sorted_values[index]


def _inside_sample_gap(start_ns: int, end_ns: int, sample_gaps: list[dict[str, float]]) -> bool:
    for gap in sample_gaps:
        if start_ns / 1e9 <= gap["from_s"] + 1e-6 and end_ns / 1e9 >= gap["to_s"] - 1e-6:
            return True
    return False


def frame_gap_stats(
    presents_ns: list[int],
    *,
    window_start_s: float | None = None,
    window_end_s: float | None = None,
    sample_gaps: list[dict[str, float]] | None = None,
) -> dict[str, Any]:
    values = sorted(set(presents_ns))
    if window_start_s is not None:
        values = [value for value in values if value / 1e9 >= window_start_s]
    if window_end_s is not None:
        values = [value for value in values if value / 1e9 <= window_end_s]
    gaps: list[tuple[float, int, int]] = []
    excluded = 0
    for previous, current in zip(values, values[1:]):
        if sample_gaps and _inside_sample_gap(previous, current, sample_gaps):
            excluded += 1
            continue
        gaps.append(((current - previous) / 1e6, previous, current))

    gap_ms = sorted(gap for gap, _, _ in gaps)
    duration_s = (values[-1] - values[0]) / 1e9 if len(values) > 1 else 0.0
    top = sorted(gaps, key=lambda item: item[0], reverse=True)[:TOP_GAP_COUNT]
    return {
        "frames": len(values),
        "duration_s": round(duration_s, 3),
        "fps": round((len(values) - 1) / duration_s, 2) if duration_s > 0 else 0.0,
        "gap_p50_ms": round(_percentile(gap_ms, 0.50), 2),
        "gap_p90_ms": round(_percentile(gap_ms, 0.90), 2),
        "gap_p99_ms": round(_percentile(gap_ms, 0.99), 2),
        "gap_max_ms": round(gap_ms[-1], 2) if gap_ms else 0.0,
        "gaps_over_ms": {str(threshold): sum(1 for gap in gap_ms if gap > threshold) for threshold in GAP_THRESHOLDS_MS},
        "top_gaps": [
            {"gap_ms": round(gap, 2), "from_s": round(start / 1e9, 3), "to_s": round(end / 1e9, 3)}
            for gap, start, end in top
        ],
        "gaps_excluded_for_sample_holes": excluded,
    }


def median(values: Iterable[float]) -> float | None:
    numbers = [value for value in values if value is not None]
    return round(statistics.median(numbers), 3) if numbers else None


def summarize_build_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    ready = [run.get("ready_seconds") for run in runs if run.get("marker_found") and run.get("ready_seconds") is not None]
    longest = [
        run.get("longest_gap_before_marker_ms")
        for run in runs
        if run.get("marker_found") and run.get("longest_gap_before_marker_ms") is not None
    ]
    return {
        "runs": len(runs),
        "runs_with_marker": len(ready),
        "ready_seconds": [round(value, 3) for value in ready],
        "ready_seconds_median": median(ready),
        "longest_gap_before_marker_ms": [round(value, 1) for value in longest],
        "longest_gap_before_marker_ms_median": median(longest),
        "am_total_time_ms": [run.get("am_total_time_ms") for run in runs if run.get("am_total_time_ms") is not None],
    }


def parse_meminfo(output: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    total = re.search(r"TOTAL PSS:\s*(\d+)\s+TOTAL RSS:\s*(\d+)", output)
    if total:
        result["total_pss_kb"] = int(total.group(1))
        result["total_rss_kb"] = int(total.group(2))
    else:
        legacy = re.search(r"^\s*TOTAL\s+(\d+)", output, re.MULTILINE)
        if legacy:
            result["total_pss_kb"] = int(legacy.group(1))
    for label, key in (("Java Heap", "java_heap_kb"), ("Native Heap", "native_heap_kb"), ("Graphics", "graphics_kb"), ("Code", "code_kb")):
        match = re.search(rf"^\s*{label}:\s*(\d+)", output, re.MULTILINE)
        if match:
            result[key] = int(match.group(1))
    return result


def parse_thermal(output: str) -> dict[str, Any]:
    status = re.search(r"Thermal Status:\s*(\d+)", output)
    temperatures = re.findall(r"Temperature\{mValue=([\d.]+), mType=(\d+), mName=([^,]+),", output)
    return {
        "thermal_status": int(status.group(1)) if status else None,
        "temperatures": [
            {"name": name, "type": int(kind), "celsius": float(value)} for value, kind, name in temperatures[:12]
        ],
    }


def parse_top_for_package(output: str, package: str) -> dict[str, Any]:
    for line in output.splitlines():
        if package in line:
            parts = line.split()
            numbers = [part for part in parts if re.fullmatch(r"\d+(\.\d+)?", part)]
            cpu = None
            for index, part in enumerate(parts):
                if part in {"S", "R", "D"} and index + 1 < len(parts):
                    try:
                        cpu = float(parts[index + 1])
                    except ValueError:
                        cpu = None
                    break
            return {"line": line.strip(), "cpu_percent": cpu, "pid": int(numbers[0]) if numbers else None}
    return {"line": "", "cpu_percent": None, "pid": None}
