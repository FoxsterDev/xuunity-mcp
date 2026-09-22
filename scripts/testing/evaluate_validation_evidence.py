#!/usr/bin/env python3
"""Evaluate release-validation evidence against an owner plan and write one acceptance report.

Exit codes: 0 accepted; 1 valid evaluation with failed, blocked or partial required rows;
2 invalid input, schema or IO. A consumer runner that maps exit code 2 to a blocked row must
instead treat this tool's exit code 2 as evaluation_invalid with no acceptance rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SCRIPT_DIR.parents[1] / "templates"
for entry in (SCRIPT_DIR, TEMPLATES_DIR):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import validation_acceptance as acceptance  # noqa: E402
from server_core import reconfigure_stdio_utf8, write_json  # noqa: E402


def _emit_compact(envelope: dict) -> None:
    from server_launcher import _bounded_compact_json

    sys.stdout.write(_bounded_compact_json(envelope))


def _emit_full(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", type=Path, help="Validation plan JSON (xuunity.light-mcp.validation-plan.v1).")
    parser.add_argument("--receipts", type=Path, help="Receipts JSON (xuunity.light-mcp.validation-receipts.v1).")
    parser.add_argument(
        "--consumer-verdict",
        type=Path,
        help="Derive plan and receipts from a consumer release verdict instead of --plan/--receipts.",
    )
    parser.add_argument("--project-id", default="consumer", help="Project id for a derived plan.")
    parser.add_argument("--plan-id", default="derived-from-consumer-verdict", help="Plan id for a derived plan.")
    parser.add_argument("--report", type=Path, required=True, help="Where the full acceptance report is written.")
    parser.add_argument("--output", choices=("compact", "full"), default="compact")
    return parser


def run(args: argparse.Namespace) -> int:
    report_path = args.report.resolve()
    try:
        if args.consumer_verdict is not None:
            if args.plan is not None or args.receipts is not None:
                raise acceptance.ValidationInputError("conflicting_inputs", "--consumer-verdict excludes --plan/--receipts")
            verdict_path = args.consumer_verdict.resolve()
            verdict, verdict_sha256 = acceptance.load_bounded_json(verdict_path)
            manifest_dir = verdict_path.parent
            plan, receipts = acceptance.derive_from_consumer_verdict(
                verdict,
                project_id=args.project_id,
                plan_id=args.plan_id,
                verdict_ref={"path": verdict_path.name, "sha256": verdict_sha256},
            )
            report_path.parent.mkdir(parents=True, exist_ok=True)
            derived_plan_path = report_path.with_name(report_path.stem + ".derived-plan.json")
            derived_receipts_path = report_path.with_name(report_path.stem + ".derived-receipts.json")
            write_json(derived_plan_path, plan)
            write_json(derived_receipts_path, receipts)
            plan_sha256 = acceptance.sha256_file(derived_plan_path)
        else:
            if args.plan is None or args.receipts is None:
                raise acceptance.ValidationInputError("missing_input", "--plan and --receipts are both required")
            plan, plan_sha256 = acceptance.load_bounded_json(args.plan.resolve())
            receipts, _ = acceptance.load_bounded_json(args.receipts.resolve())
            manifest_dir = args.receipts.resolve().parent
        acceptance.validate_plan(plan)
        acceptance.validate_receipts(receipts)
        report = acceptance.evaluate(
            plan,
            receipts,
            manifest_dir=manifest_dir,
            plan_sha256=plan_sha256,
            report_ref=report_path.name,
        )
        acceptance.validate_acceptance_report(report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(report_path, report)
        exit_code = acceptance.exit_code_for(report)
        if args.output == "full":
            _emit_full(report)
        else:
            _emit_compact(acceptance.compact_envelope(report, exit_code=exit_code, report_path=str(report_path)))
        return exit_code
    except (acceptance.ValidationInputError, OSError, ValueError) as exception:
        envelope = acceptance.invalid_envelope(exception, report_path=None)
        if args.output == "full":
            _emit_full(envelope)
        else:
            _emit_compact(envelope)
        return 2


def main(argv: list[str] | None = None) -> int:
    reconfigure_stdio_utf8()
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
