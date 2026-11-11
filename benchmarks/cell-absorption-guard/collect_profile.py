#!/usr/bin/env python3
"""Read a separate normal-binary sample without turning stack counts into time."""
import json
from pathlib import Path
import runpy
import sys

HERE = Path(__file__).resolve().parent
helpers = runpy.run_path(str(HERE / "measure.py"))
parser = runpy.run_path(str(HERE.parent / "raytrace-thread-bottlenecks/collect.py"))
read, sha = helpers["read"], helpers["sha"]


def collect(root, output):
    diagnostic = read(root / "diagnostic.json")
    timing = read(HERE / "timing.json")
    lane = timing["cases"]["ray"]["lanes"]["on"]
    assert diagnostic["runtime_sha256"] == timing["runtime_sha256"]["current"]
    assert diagnostic["program_file_sha256"] == timing["cases"]["ray"]["program_sha256"]
    assert diagnostic["state_sha256"] == timing["cases"]["ray"]["references"]["current"]["state_sha256"]
    assert diagnostic["schedule_sha256"] == lane["executed_schedule_sha256"]
    assert diagnostic["key_lookup_calls"] == lane["queries"]
    for key, value in lane["execution_counts"].items():
        assert diagnostic["stats"][key] == value
    report = read(root / "runtime/report.json")
    assert not report["query_rule_profile"], "profile flag must not disable ReadySets"
    assert not report.get("allocations")
    raw = read(root.parent / "timing/samples.json")["cases"]["ray"]["lanes"]["on"]["samples"][0]
    assert report["free_join"] == raw["free_join_stats"]
    assert report["entry_schedule"]["stats"] == raw["entry_schedule_stats"]
    assert sha(root / "stacks.txt") == diagnostic["sample"]["stacks_sha256"]
    threads = parser["sample_threads"](root / "stacks.txt", expected_threads=1)
    main = threads[0]
    inference = main["inclusive"]["eggfuse_cell_runtime::executor::Executor::execute_until"]
    selected = ("Executor::matches", "Scheduler::batches", "FreeJoin::admit", "QueryIndexes::single_projection",
        "QueryIndexes::candidates", "QueryIndexes::publish_table", "publish_finished_tables", "Columns::put",
        "Columns::remove", "repair_selected", "Context::neighborhood", "lookup_port_key", "owned_candidates")
    result = {k: diagnostic[k] for k in ("scope", "args", "runs", "state_sha256", "schedule_sha256",
              "runtime_sha256", "program_file_sha256", "sample")}
    result["inference_stack_samples"] = inference
    result["selected_inclusive"] = {key: sum(n for symbol, n in main["inference_inclusive"].items()
                                               if symbol.endswith(key)) for key in selected}
    result["threads"] = threads
    result["full_run_gating_counts"] = {
        "free_join": report["free_join"],
        "sieve": {k: v for k, v in report["sieve"]["stats"].items() if isinstance(v, (int, float))},
        "entry": {k: v for k, v in report["entry_schedule"]["stats"].items() if isinstance(v, (int, float))},
    }
    result["progress_logging_stack_samples"] = main["inference_inclusive"].get("std::io::stdio::_eprint", 0)
    result["report_sha256"] = sha(root / "runtime/report.json")
    result["limits"] = "One five-second window triggered at inference start, not a full-run census. Inclusive stacks overlap and cannot be added. Optimized inlining limits attribution. Progress logging and sampling perturb this diagnostic. No CELL_CPU_PROFILE: normal ReadySets scheduling and work are preserved. These counts are not timing samples or CPU percentages."
    output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("run without Python -O")
    collect(*map(Path, sys.argv[1:]))
