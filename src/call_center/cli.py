"""Command-line entry point: ``call-center analyze <file> [--out DIR]``."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from call_center.config import format_config_error, load_settings
from call_center.graph import run_pipeline


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
        load_settings()
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

    state = run_pipeline(str(source))
    report = {
        "source_file": state["source_file"],
        "status": "stub",
        "stages_completed": state["stages_completed"],
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{source.stem}.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
