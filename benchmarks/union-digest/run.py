#!/usr/bin/env python3
"""Fresh-process AB/BA experiment; audit and state exports are not timed.

Build the fixture example and runtime first (see README). Optional --baseline
is an executable built from the pristine parent, copied before this change.
"""
import argparse
import hashlib
import json
import platform
import statistics
import subprocess
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(value):
    if isinstance(value, list):
        return [normalize(x) for x in value]
    if isinstance(value, dict):
        result = {k: normalize(v) for k, v in value.items()}
        for field in ("rows", "anchors"):
            if field in result:
                result[field].sort(key=lambda r: json.dumps(r, sort_keys=True))
        return result
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--runtime", type=Path, default=Path("target/release/eggfuse-cell-runtime"))
    ap.add_argument("--fixture", type=Path, default=Path("target/release/examples/union_digest_fixture"))
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--repeat", type=int, default=7)
    ap.add_argument("--groups", type=int, default=256)
    ap.add_argument("--depth", type=int, default=32)
    args = ap.parse_args()
    if min(args.repeat, args.groups, args.depth) <= 0:
        ap.error("repeat, groups and depth must be positive")
    args.output.mkdir()
    lanes = {"control": (args.runtime, []), "digest": (args.runtime, ["--union-digest"])}
    if args.baseline:
        lanes["parent"] = (args.baseline, [])
    report = {"scope": "standalone Cell CPU; constructor-only synthetic workloads, no marker Bake or egglog runtime timing",
              "platform": platform.platform(), "groups": args.groups, "depth": args.depth,
              "repeat": args.repeat,
              "binaries_sha256": {lane: sha256(binary) for lane, (binary, _) in lanes.items()},
              "fixture_sha256": sha256(args.fixture), "cases": {}}
    for shape in ("chain", "fanout", "stable"):
        directory = args.output / shape
        subprocess.run([str(args.fixture), str(directory), shape, str(args.groups), str(args.depth)], check=True)
        program = directory / "program.json"

        def run(lane, suffix, audit=False):
            binary, flags = lanes[lane]
            out = directory / f"{lane}-{suffix}"
            cmd = [str(binary), "--program", str(program), "--output", str(out), *flags]
            if audit:
                cmd.append("--audit-stages")
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
            return out, read(out / "report.json")

        # Audit once, outside the timing samples. Exact identities are stable
        # for these fixtures; the Rust tests separately check arbitrary renaming.
        audit_dirs = {lane: run(lane, "audit", True)[0] for lane in lanes}
        for filename in ("state.json", "stages.json", "binding-audit.json"):
            expected = normalize(read(audit_dirs["control"] / filename))
            for lane, directory_audit in audit_dirs.items():
                assert normalize(read(directory_audit / filename)) == expected, (shape, lane, filename)
        def schedule(result):
            return [{key: step[key] for key in (
                "ruleset", "path", "iterations", "ordinal", "epoch", "changed",
                "logical_matches", "executed_bindings")} for step in result["steps"]]
        expected_schedule = schedule(read(audit_dirs["control"] / "report.json"))
        for directory_audit in audit_dirs.values():
            assert schedule(read(directory_audit / "report.json")) == expected_schedule
        samples = {lane: [] for lane in lanes}
        for lane in lanes:
            run(lane, "warmup")
        for iteration in range(args.repeat):
            order = list(lanes)
            if iteration % 2:
                order.reverse()
            for lane in order:
                _, result = run(lane, str(iteration))
                assert schedule(result) == expected_schedule
                samples[lane].append({key: result[key] for key in (
                    "setup_seconds", "inference_seconds", "peak_rss_through_inference_bytes")})
        case = {"audit": "initial/per-Run/final rows, bindings and semantic schedule equal across lanes",
                "program_file_sha256": sha256(program),
                "source_sha256": sha256(directory / "source.egg"), "lanes": {}}
        for lane in lanes:
            result = read(audit_dirs[lane] / "report.json")
            case["lanes"][lane] = {"samples": samples[lane], "stats": result["stats"],
                "union_digest": result.get("union_digest"),
                "median": {key: statistics.median(s[key] for s in samples[lane]) for key in samples[lane][0]}}
        report["cases"][shape] = case
        (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        print(shape, {lane: case["lanes"][lane]["median"] for lane in lanes}, flush=True)


if __name__ == "__main__":
    main()
