#!/usr/bin/env python3
"""Account for singleton takeovers and check their saved source-Run premises."""
from collections import Counter
import json
from pathlib import Path
import sys

from collect import stable_steps
from collect_rejections import read, sha


def windows(root, before, reviewed):
    result = []
    assert read(root/"windows/checks.json")["state_sha256"] == read(before/"windows/checks.json")["state_sha256"]
    assert stable_steps(read(root/"windows/report.json")) == stable_steps(read(before/"windows/report.json"))
    for path in sorted((root/"windows").glob("run-*.json.gz")):
        assert sha(before/"windows"/path.name) == reviewed["source_windows"]["artifacts_sha256"][path.name]
        a,b = read(before/"windows"/path.name),read(path)
        assert a["before"] == b["before"] and a["after"] == b["after"], path.name
        assert (a["unions_before"],a["unions_after"]) == (b["unions_before"],b["unions_after"])
        def writes(w):
            return [{**v,"source":None if v["source"] is None else v["source"][1]}
                    for v in w["capture"]["effective_writes"]]
        assert writes(a) == writes(b), (path.name,"ordered actual mutations")
        sizes = {r["values"][0]["Eq"]:r["values"][1]["Int"] for r in a["before"]
                 if r["table"] == "Expr-size" and not r["hidden"]}
        uses = Counter(r["values"][0]["Eq"] for r in a["before"] if r["table"] == "Get" and not r["hidden"])
        def binding(v): return {k:x for k,x in v.items() if k != "ordinal"}
        new = b["capture"]["matches"]
        position = removed = 0
        for match in a["capture"]["matches"]:
            if position < len(new) and binding(match) == binding(new[position]):
                position += 1
            else:
                assert match["rule"] == 153 and not match["direct"], (path.name,"uncovered match removed")
                values = match["values"]
                assert uses[values["0"]["Eq"]] == 1, (path.name,"not a singleton input")
                assert sizes[values["2"]["Eq"]] <= values["3"]["Int"], (path.name,"not absorbed at Run start")
                removed += 1
        assert position == len(new), (path.name,"new or reordered matching")
        result.append({"run":a["run"],"additional_absorbed_singletons":removed,
            "exact_states_and_ordered_mutations":True,"artifacts_sha256":[sha(before/"windows"/path.name),sha(path)]})
    assert len(result) == 14 and sum(w["additional_absorbed_singletons"] for w in result) > 0
    return result


def collect(root, output):
    before = root.parent/"cell-absorption-rejection"
    reviewed = read(Path(__file__).resolve().parent/"rejections.json")
    acceptance = read(root/"semantic-acceptance.json")
    assert acceptance["status"] == "pass"
    assert acceptance["input_sha256"]["cpu_values"] == sha(root/"sum/state.json")
    result = {"baseline_commit":"5102adda", "scope":"standalone Cell CPU; work and allocation evidence, no timing claim",
              "cases":{}, "native_sum_acceptance_sha256":sha(root/"semantic-acceptance.json")}
    for case in ("sum","ray1280","ray-full"):
        assert sha(before/case/"report.json") == reviewed["cases"][case]["reports_sha256"][1]
        a,b = (read(p/case/"report.json") for p in (before,root))
        assert a["program_sha256"] == b["program_sha256"]
        assert a["prefix_configuration"] == b["prefix_configuration"]
        assert sha(before/case/"state.json") == sha(root/case/"state.json"), case
        assert stable_steps(a) == stable_steps(b)
        for k in ("function_updates","unions","logical_facts_created","constructor_requests","constructor_reused"):
            assert a["stats"][k] == b["stats"][k], (case,k)
        assert a["key_lookup_calls"] == b["key_lookup_calls"]
        x,y = (r["neighbor_context"]["absorption"] for r in (a,b))
        assert x["condition_bytes_per_neighborhood"] == y["condition_bytes_per_neighborhood"] == 32
        for k in ("checks","groups_absorbed","reused_bounds","output_probes","rejection_reads","rejection_hits"):
            assert x["stats"][k] == y["stats"][k], (case,k)
        s = dict(y["stats"])
        assert not any(s.pop("pending"))
        n = s["single_absorbed"]
        assert n > 0 and s["matches_absorbed"] == x["stats"]["matches_absorbed"]+n
        for k in ("bindings","single_writes"):
            assert a["stats"][k]-b["stats"][k] == n, (case,k)
        assert sum(s["executed_bindings"] for s in a["steps"])-sum(s["executed_bindings"] for s in b["steps"]) == n
        for k in ("completed_steps","absorbed_root_completions"):
            assert a["stage_spine"]["stats"][k]-b["stage_spine"]["stats"][k] == n, (case,k)
        assert a["stage_spine"]["stats"]["resumed_steps"] == b["stage_spine"]["stats"]["resumed_steps"]
        assert a["entry_schedule"]["stats"]["staged_root_records"]-b["entry_schedule"]["stats"]["staged_root_records"] == n
        result["cases"][case] = {"runs":len(b["steps"]),"exact_state_and_logical_runs":True,
            "state_sha256":sha(root/case/"state.json"),"conditions":s,
            "additional_executions_omitted":n,
            "additional_target_lookups_net":s["single_output_probes"]-n,
            "allocations":{k:[a["allocations"][k],b["allocations"][k]] for k in ("alloc_calls","realloc_calls","requested_bytes")},
            "entry":{k:[a["entry_schedule"]["stats"][k],b["entry_schedule"]["stats"][k]] for k in
                     ("entry_publication_writes","publication_slot_probes","staged_root_records","staged_root_redirects")},
            "report_sha256":[sha(p/case/"report.json") for p in (before,root)]}
    result["source_windows"] = windows(root,before,reviewed)
    result["binaries"] = {name:sha(root/name) for name in ("prefix","observer")}
    output.write_text(json.dumps(result,indent=2)+"\n")


if __name__ == "__main__":
    if not __debug__: raise SystemExit("run without Python -O")
    collect(*map(Path,sys.argv[1:]))
