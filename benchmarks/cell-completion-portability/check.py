#!/usr/bin/env python3
"""Check independent artifact loading and saved executions; no timing runs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integers(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            if key not in ("steps", "storage") and not key.startswith("peak_rss_"):
                yield from integers(child, path + "/" + key)
    elif type(value) is int:
        yield path, value


def main(root, output):
    identity = read(root / "baseline-identity.json")
    require(sha(root / "runtime-before") == identity["runtime_sha256"], "baseline binary changed")
    inspections = []
    for binary, artifact, success in (
        ("runtime-before", "old-program.json", False),
        ("runtime-before", "compiled/program.json", True),
        ("runtime-after", "compiled/program.json", True),
    ):
        result = subprocess.run([str((root / binary).resolve()), "--program",
            str(root / artifact), "--inspect-program"], capture_output=True, text=True)
        require(result.returncode == (0 if success else 1), "unexpected inspection exit")
        if not success:
            require("invalid ripsat completion structures" in result.stderr, "wrong rejection")
        inspections.append({"binary": binary, "binary_sha256": sha(root / binary),
            "artifact": artifact, "artifact_file_sha256": sha(root / artifact),
            "program_sha256": read(root / artifact)["sha256"],
            "exit_code": result.returncode, "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()})
    reports = {name: read(root / name / "report.json") for name in ("shipped", "control", "normal")}
    keys = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")
    signature = lambda report: [[step[key] for key in keys] for step in report["steps"]]
    state = read(root / "normal/state.json")
    for name, report in reports.items():
        require(report["status"] == "complete" and len(report["steps"]) == 1428, "incomplete " + name)
        require(read(root / name / "state.json") == state, "changed final graph " + name)
        require(signature(report) == signature(reports["normal"]), "changed ordered Runs " + name)
    control = dict(integers(reports["control"]))
    require(control == dict(integers(reports["normal"])), "runtime work or layout changed")
    acceptance = read(root / "semantic-acceptance.json")
    require(acceptance["status"] == "pass", "native choice acceptance did not pass")
    fields = ("history_allocations", "joint_history_frames", "joint_history_query_reads",
        "joint_history_query_writes", "ripsat_completed", "ripsat_plan_probes",
        "ripsat_layout_checks", "ripsat_witness_checks", "ripsat_witness_fallbacks")
    result = {
        "scope": "standalone Cell CPU sum-bits, artifact portability and work counts; not speed admission",
        "baseline": identity, "inspection": inspections,
        "same_program_integer_counters_and_layouts": len(control),
        "same_program_counter_differences": 0, "ordered_runs": 1428,
        "semantic_acceptance": "pass", "semantic_acceptance_sha256": sha(root / "semantic-acceptance.json"),
        "reports": {name: {"program_sha256": report["program_sha256"],
            "report_file_sha256": sha(root / name / "report.json"),
            "state_file_sha256": sha(root / name / "state.json"),
            "key_lookup_calls": report["key_lookup_calls"],
            "handoff_attempts": report["stats"]["handoff_attempts"],
            "completion_work": {key: report["stage_spine"]["stats"][key] for key in fields}}
            for name, report in reports.items()},
    }
    output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: check.py ARTIFACT_ROOT OUTPUT.json")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
