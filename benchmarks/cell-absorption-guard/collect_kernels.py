#!/usr/bin/env python3
"""Verify saved Cell-kernel absorption dispatch results; no timing campaign."""
import json
from pathlib import Path
import sys

from collect_rejections import counts, read, sha, steps


def collect(root, output):
    before = root.parent/"cell-absorption-singletons"
    reviewed = read(Path(__file__).resolve().parent/"singletons.json")
    acceptance = read(root/"semantic-acceptance.json")
    assert acceptance["status"] == "pass"
    assert acceptance["input_sha256"]["cpu_values"] == sha(root/"cli-sum/state.json")
    assert read(root/"cli-sum/state.json") == read(root/"sum/state.json")
    cli = read(root/"cli-sum/report.json")
    prefix = read(root/"sum/report.json")
    assert cli["neighbor_context"]["absorption"]["enabled"]
    assert cli["stats"] == prefix["stats"] and steps(cli) == steps(prefix)
    result = {"baseline_commit":"af30e99f", "scope":"standalone Cell CPU; no new timing or sparsity claim",
              "native_sum_acceptance_sha256":sha(root/"semantic-acceptance.json"),"cases":{}}
    for case in ("sum","ray1280","ray-full"):
        assert sha(before/case/"report.json") == reviewed["cases"][case]["report_sha256"][1]
        a,b = (read(p/case/"report.json") for p in (before,root))
        assert sha(before/case/"state.json") == sha(root/case/"state.json"), case
        for key in ("program_sha256","prefix_configuration","stats","key_lookup_calls"):
            assert a[key] == b[key], (case,key)
        assert steps(a) == steps(b)
        for key in ("stage_spine","entry_schedule"):
            assert counts(a[key]["stats"]) == counts(b[key]["stats"]), (case,key)
        x,y = (r["neighbor_context"]["absorption"] for r in (a,b))
        assert x["plans"] == y["plans"]
        assert x["condition_bytes_per_neighborhood"] == y["condition_bytes_per_neighborhood"] == 32
        for key in x["stats"]:
            if key != "single_candidates": assert x["stats"][key] == y["stats"][key], (case,key)
        assert y["stats"]["single_candidates"] == y["stats"]["single_checks"]
        assert not any(y["stats"]["pending"])
        allocations = {k:[a["allocations"][k],b["allocations"][k]]
                       for k in ("alloc_calls","realloc_calls","requested_bytes")}
        frames = {k:[a["query_workers"]["stats"][k],b["query_workers"]["stats"][k]]
                  for k in ("frame_allocations","worker_frame_capacity_bytes")}
        assert allocations["alloc_calls"][0] == allocations["alloc_calls"][1]
        assert allocations["realloc_calls"][1]-allocations["realloc_calls"][0] == frames["frame_allocations"][1]-frames["frame_allocations"][0]
        result["cases"][case] = {"runs":len(b["steps"]),"exact_state_work_and_ordered_runs":True,
            "state_sha256":sha(root/case/"state.json"),
            "single_guard_calls":[x["stats"]["single_candidates"],y["stats"]["single_candidates"]],
            "checks_reusing_existing_domain_lookup":y["stats"]["checks"],
            "executions_omitted":y["stats"]["matches_absorbed"],
            "compiled_metadata":{k:y[k] for k in ("plans","capability_entries","compiled_capability_bytes","removed_context_plan_bytes","condition_bytes_per_neighborhood")},
            "allocations":allocations,"worker_scratch":frames,
            "reports_sha256":[sha(p/case/"report.json") for p in (before,root)]}
    result["cli"] = {"enabled":True,"state_sha256":sha(root/"cli-sum/state.json"),
                     "report_sha256":sha(root/"cli-sum/report.json"),"exact_prefix_state_work_and_runs":True}
    result["source_boundary_coverage"] = "50 selected integration tests include source-Run snapshots; no new Raytrace window capture. Prior 14-window evidence remains scoped to af30e99f."
    result["binaries"] = {name:sha(root/name) for name in ("prefix","runtime")}
    output.write_text(json.dumps(result,indent=2)+"\n")


if __name__ == "__main__":
    if not __debug__: raise SystemExit("run without Python -O")
    collect(*map(Path,sys.argv[1:]))
