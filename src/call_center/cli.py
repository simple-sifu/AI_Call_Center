"""Command-line entry point: ``call-center analyze <file> [--out DIR]``."""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from call_center.config import format_config_error, load_settings
from call_center.graph import run_pipeline
from call_center.tracing import configure_tracing, flush_traces


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="call-center")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="analyze a call recording")
    analyze.add_argument("file", help="path to the call audio file")
    analyze.add_argument("--out", default="reports", help="report output directory")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = load_settings()
    except ValidationError as error:
        print(f"invalid configuration: {format_config_error(error)}", file=sys.stderr)
        return 2
    source = Path(args.file)
    if not source.exists():
        print(f"file not found: {args.file}", file=sys.stderr)
        return 2
    if not source.is_file():
        print(f"not a file: {Path(args.file)}", file=sys.stderr)
        return 2

    tracing = configure_tracing(settings)
    try:
        state = run_pipeline(str(source), report_output_dir=args.out)
    finally:
        if tracing:
            flush_traces()

    report_path = state.get("report_json_path")
    if not report_path:
        print("report stage did not write a JSON file", file=sys.stderr)
        return 2
    print(report_path)

    if state["status"] == "failed":
        print(state["status_reason"] or "failed", file=sys.stderr)
        return 2
    if state["status"] == "blocked":
        print(f"blocked: {state['status_reason'] or 'no reason given'}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
