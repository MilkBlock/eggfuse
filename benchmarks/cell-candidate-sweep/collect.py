#!/usr/bin/env python3
"""Summarize saved Bake executions; never launch a workload or infer latency."""
import hashlib
import json
import pathlib
import sys


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


AUDITS = (
    "final_state_sha256", "schedule_sha256", "ordered_rhs_sha256",
    "ordered_writes_sha256", "ordered_resumes_sha256",
)
COUNTERS = (
    "key_lookup_calls", "stats/constructor_requests", "stats/union_requests",
    "stage_spine/stats/history_allocations",
    "stage_spine/stats/history_capture_reads",
    "stage_spine/stats/history_slots_written",
    "stage_spine/stats/joint_history_frames",
    "stage_spine/stats/joint_history_query_reads",
    "stage_spine/stats/joint_history_query_writes",
    "stage_spine/stats/joint_output_reads",
    "stage_spine/stats/ripsat_witness_checks",
    "stage_spine/stats/ripsat_layout_checks",
    "stable_ports/stats/port_reads",
    "stable_ports/stats/root_parent_probes",
)


def collect(root):
    experiments = {}
    reference = None
    for name in ("full-round", "continued", "canonical", "shipped-resume"):
        folder = root / name
        rounds = read(folder / "rounds.json")
        program = read(folder / "program.json")
        summaries = []
        for row in rounds:
            stamp = {key: row[key] for key in AUDITS}
            if any(not isinstance(s, str) or len(s) != 64 for s in stamp.values()):
                raise ValueError(f"{name}: missing execution audit digest")
            if reference is None:
                reference = stamp
            if reference != stamp:
                raise ValueError(f"{name}: graph or ordered execution changed")
            credit = row["credit"]
            trials = []
            for trial in credit.get("trials", []):
                if trial["semantic_audit"] is not True:
                    raise ValueError(f"{name}: trial execution audit failed")
                work = trial["work"]
                trials.append({
                    "join": trial["join"],
                    "program_sha256": trial["program_sha256"],
                    "net_saved_operations": work["net_saved_operations"],
                    "selected_counter_deltas": {
                        key: work["counters"][key] for key in COUNTERS
                    },
                })
            history_file = folder / f"round-{row['round']}" / "cell-history.json"
            history = read(history_file)
            if history["program_sha256"] != row["source_program"]:
                raise ValueError(f"{name}: history belongs to another program")
            contracts = history["contracts"]
            structures = contracts["structures"]
            opaque = {
                i for i, structure in enumerate(structures)
                if structure.get("normalization") == "opaque-source-contract"
            }
            implementations = {x["unit"]: x for x in contracts["implementations"]}
            event_units = history["event_units"]
            if len(event_units) != len(history["events"]):
                raise ValueError(f"{name}: event/implementation length mismatch")
            summaries.append({
                "round": row["round"], "units": row["units"],
                "source_program": row["source_program"], "stop": row["stop"],
                "ranked_proposals": credit.get("ranked_proposals"),
                "untried_ranked_proposals": credit.get("untried_ranked_proposals"),
                "duplicate_executable_proposals": credit.get("duplicate_executable_proposals"),
                "selected_net_saved_operations": credit.get("selected_net_saved_operations"),
                "trials": trials, "completion_entries": row["completion_entries"],
                "history": {
                    "file_sha256": digest(history_file),
                    "structures": len(structures), "opaque_structures": len(opaque),
                    "sampled_events": len(event_units),
                    "opaque_sampled_events": sum(
                        implementations[unit]["class"] in opaque for unit in event_units
                    ),
                    "dropped_events": history["dropped_events"],
                    "scope": history["scope"],
                },
            })
        experiments[name] = {
            "rounds_file_sha256": digest(folder / "rounds.json"),
            "final_program_sha256": program["sha256"],
            "limits": program["iterative_bake"]["limits"],
            "execution": {key: rounds[0]["credit"][key] for key in (
                "entry_publications", "repair_ports", "stable_ports", "local_congruence"
            )},
            "rounds": summaries,
        }
    if experiments["continued"]["rounds"][0]["source_program"] != experiments["full-round"]["final_program_sha256"]:
        raise ValueError("continuation did not resume the selected artifact")
    return {
        "scope": "saved short sum-bits executions of standalone Cell CPU at 15de6b94; not native egglog or latency admission",
        "audit_scope": "compiler-recorded exact graph, schedule and ordered RHS/write/resume audits; not a new native semantic acceptance",
        "common_execution_audits": reference,
        "experiments": experiments,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: collect.py ARTIFACT_ROOT OUTPUT.json")
    result = collect(pathlib.Path(sys.argv[1]))
    pathlib.Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n")
