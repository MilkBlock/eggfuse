#!/usr/bin/env python3
"""Compare saved runtime heaps and classify remaining ordinary source frames.

These are observed lifetime relationships, not proof that an Entry or publication
may be skipped. Keep logical fact identity separate from physical source records.
"""
import collections
import json
import pathlib
import sys


def audit(root):
    rows = []
    for name in ("fact", "loopfact", "sum-bits", "dot-product"):
        directory = root / name
        before = json.loads((directory / "candidate-scalar-heap.json").read_text())
        after = json.loads((directory / "candidate-live-parent-owner-heap.json").read_text())
        assert before["program_sha256"] == after["program_sha256"]
        assert before["final_state_sha256"] == after["final_state_sha256"]
        frames = {f["cell"]: f for f in after["source_storage"]["fact_lifecycle"]["frames"]}
        components = after["ownership_storage"]["components"]
        component_of = {f: c["id"] for c in components for f in c["frames"]}
        counts = collections.Counter()
        component_members = {c["id"]: c["frames"] for c in components}
        uncovered_widths = collections.Counter()
        uncovered_templates = collections.Counter()
        for cell, frame in frames.items():
            if frame["completed_storage"]:
                counts["shared_storage"] += 1
                continue
            if not frame["completed"]:
                counts["not_completed"] += 1
                continue
            parent = frame["parent"]
            if parent is not None:
                same = cell in component_of and component_of.get(parent["cell"]) == component_of[cell]
                counts["parent_inside_component" if same else "parent_outside_component"] += 1
                source = frames.get(parent["cell"])
                cross = source is not None and source["started_epoch"] != frame["started_epoch"]
                if same and cross:
                    counts["internal_cross_stage_parents"] += 1
                continue
            counts["no_parent_remaining"] += 1
            members = component_members.get(component_of.get(cell), [])
            uncovered_widths[len(members)] += 1
            uncovered_templates[frame["template"]] += 1
            if any(f in frames and not frames[f]["completed"] for f in members if f != cell):
                counts["no_parent_with_uncompleted_neighbor"] += 1
        source = after["source_storage"]
        assert len(frames) - counts["shared_storage"] == source["completed_owners"]["source_records"]
        metrics = {k: v for k, v in after["completion_work"].items() if k.startswith("shared_owner_")}
        rows.append({"case": name, "program": after["program_sha256"], "runs": after["runs"],
                     "graph_before": before["graph_owned_teardown_bytes"], "graph_after": after["graph_owned_teardown_bytes"],
                     "source_records_before": before["source_storage"]["completed_owners"]["source_records"],
                     "source_records_after": source["completed_owners"]["source_records"],
                     "logical_frames_before": len(before["source_storage"]["fact_lifecycle"]["frames"]),
                     "logical_frames_after": len(frames),
                     "logical_facts_before": sum(len(f["facts"]) for f in before["source_storage"]["fact_lifecycle"]["frames"]),
                     "logical_facts_after": sum(len(f["facts"]) for f in frames.values()),
                     "completed_storage_before": before["source_storage"]["completed_owners"]["completed_frames"],
                     "completed_storage_after": source["completed_owners"]["completed_frames"],
                     "max_takeover_extra_before": before["max_takeover_extra_bytes"],
                     "max_takeover_extra_after": after["max_takeover_extra_bytes"],
                     "program_bytes_delta": after["retained_program_teardown_bytes"] - before["retained_program_teardown_bytes"],
                     "work": metrics, "remaining_source_classification": dict(counts),
                     "no_parent_component_widths": dict(uncovered_widths),
                     "no_parent_templates": dict(uncovered_templates)})
    return {"scope": "actual standalone Cell runtime; fixed batched catalog; physical owner extension, no RHS skip or speed claim",
            "cases": rows, "limits": "Logical source IDs and fact states remain; internal-parent observations need typed projection and lifecycle proof before contraction."}


if __name__ == "__main__":
    root, output = map(pathlib.Path, sys.argv[1:])
    output.write_text(json.dumps(audit(root), indent=2) + "\n")
