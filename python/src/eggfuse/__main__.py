"""Offline utilities for the two-Run neural experiment."""
import argparse
import json
from pathlib import Path

from . import compile_projection, verify_crossrun


def main():
    parser = argparse.ArgumentParser(prog="python -m eggfuse")
    commands = parser.add_subparsers(dest="command", required=True)
    compile_cmd = commands.add_parser("compile", help="compile a scheduled .egg program to plan.json")
    compile_cmd.add_argument("source", type=Path)
    compile_cmd.add_argument("--compiler-binary", required=True, type=Path)
    compile_cmd.add_argument("--output", required=True, type=Path)
    verify_cmd = commands.add_parser("verify", help="check saved make/finish predictions")
    verify_cmd.add_argument("--plan", required=True, type=Path)
    verify_cmd.add_argument("--input", required=True, type=Path)
    verify_cmd.add_argument("--predictions", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "compile":
        compile_projection(args.source, compiler_binary=args.compiler_binary, output_path=args.output)
        return
    source = json.loads(args.input.read_text())
    stages = json.loads(args.predictions.read_text())
    report = verify_crossrun(args.plan, source["a"], source["b"], source["requests"],
                             stages["make"], stages["finish"])
    print(json.dumps(report))
    if report["both_complete_graphs"] != report["run2"]["graphs"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
