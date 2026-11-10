#!/usr/bin/env python3
"""Validate saved short runs and account for constructor coverage and costs."""
import hashlib
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


FIELDS = (
    "entries", "point_reads", "spine_entries", "spine_point_reads", "answers",
    "coordinator_entries", "worker_entries", "cell_task_probes", "cell_task_records",
    "cell_task_links", "cell_task_emissions", "borrowed_job_headers", "chunks",
    "completion_headers", "winner_order_comparisons", "answer_buffer_allocations",
    "frame_allocations", "entry_buffer_bytes", "peak_cell_queue_bytes",
    "peak_cell_task_bytes", "frame_capacity_bytes", "output_buffer_capacity",
)
RUN_FIELDS = ("ordinal", "ruleset", "path", "iterations", "epoch",
    "logical_matches", "executed_bindings", "changed")
GROUPS = (
    ("sum-before4", "sum-after1", "sum-after4", "sum-off"),
    ("stable-before4", "stable-after4"),
    ("completed-before4", "completed-after4"),
    ("ray128-before4", "ray128-after1", "ray128-after4", "ray128-off"),
)


def main(root, output):
    reports = {}
    evidence = {}
    for group in GROUPS:
        graph = read(root / group[0] / "state.json")
        baseline = read(root / group[0] / "report.json")
        runs = 128 if group[0].startswith("ray128") else 1428
        signature = lambda r: [[s[k] for k in RUN_FIELDS] for s in r["steps"]]
        for name in group:
            report = read(root / name / "report.json")
            require(report["status"] == ("checkpointed" if runs == 128 else "complete"), name + " status")
            require(len(report["steps"]) == runs, name + " Run count")
            require(report["program_sha256"] == baseline["program_sha256"], name + " different program")
            require(read(root / name / "state.json") == graph, name + " final graph differs")
            require(signature(report) == signature(baseline), name + " ordered Runs differ")
            require(report["key_lookup_calls"] == baseline["key_lookup_calls"], name + " logical query count changed")
            w = report["query_workers"].get("stats", {})
            if w:
                require(sum(w["worker_entries"]) + w["coordinator_entries"] == w["entries"], name + " Entry ownership")
            reports[name] = report
            evidence[name] = {
                "program_sha256": report["program_sha256"], "runs": runs,
                "report_sha256": sha(root / name / "report.json"),
                "state_sha256": sha(root / name / "state.json"),
                "key_lookup_calls": report["key_lookup_calls"],
                "pre_resume_port_lookups": report["stage_spine"]["stats"]["pre_resume_port_lookups"],
                "ripsat_completed": report["stage_spine"]["stats"]["ripsat_completed"],
                "workers": {key: w[key] for key in FIELDS if key in w},
                "constructor_work": w.get("constructors", {}),
            }
    for name in ("sum-after1", "sum-after4", "completed-after4", "ray128-after1", "ray128-after4"):
        work = reports[name]["query_workers"]["stats"]["constructors"]
        require(work["canonical_lookups"] > 0 and work["lookups"] == 0, name + " wrong constructor backend")
    stable = reports["stable-after4"]["query_workers"]["stats"]["constructors"]
    require(stable["canonical_lookups"] == 0 and stable["lookups"] > 0, "stable path not preserved")
    require(evidence["completed-after4"]["ripsat_completed"] == evidence["completed-before4"]["ripsat_completed"] == 165,
        "direct completion lost coverage")
    for name in ("sum-after4", "ray128-after4"):
        require(all(reports[name]["query_workers"]["stats"]["worker_entries"]), name + " idle worker")
    acceptance = read(root / "semantic-acceptance.json")
    require(acceptance["status"] == "pass", "native sum-bits acceptance failed")
    result = {
        "baseline_commit": "634d082e",
        "scope": "standalone Cell CPU; full short sum-bits and only 128 Raytrace Runs; no speed claim",
        "binaries": {name: sha(root / name) for name in ("runtime-before", "runtime-after", "prefix-before", "prefix-after")},
        "programs": {name: {"file_sha256": sha(root / name), "program_sha256": read(root / name)["sha256"]}
            for name in ("sum-program.json", "ray-program.json")},
        "semantic_acceptance": {"status": "pass", "file_sha256": sha(root / "semantic-acceptance.json")},
        "source_run_graph_audit": "integration fixtures; saved workload runs compare final graph and all ordered Run metadata",
        "cases": evidence,
    }
    output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: collect.py ARTIFACT_ROOT OUTPUT.json")
    main(Path(sys.argv[1]), Path(sys.argv[2]))
