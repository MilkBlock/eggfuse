"""Collect paired native data without treating equal coverage counts as equal graphs."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median


def facts(row):
    return {json.dumps(f, sort_keys=True) for f in row["facts"]}


def summarize(out):
    paths = sorted((*out.glob("high-*-b*.json"), *out.glob("*-p*-b*.json")))
    groups = defaultdict(list)
    archive = out / "runs.jsonl"
    if paths:
        evidence = [dict(json.loads(p.read_text()), file=p.name) for p in paths]
    else:
        evidence = [json.loads(line) for line in archive.read_text().splitlines()]
    if not evidence:
        raise ValueError("no completed native measurements")
    for row in evidence:
        assert row["termination"] == "schedule_end", (row["file"], row["termination"])
        groups[
            row["case"],
            row["arm"],
            row.get("steps", 0),
            row.get("pages", 0),
            row.get("primitive_only", False),
            row.get("fresh_requests", False),
        ].append(row)
    rows = []
    for (case, arm, steps, pages, bare, fresh), pair in sorted(groups.items()):
        assert sorted(r["block"] for r in pair) == [0, 1]
        ref = groups.get((case, "A", 0, 0, False, False))
        a = pair[0]
        assert all(
            r["state_sha"] == a["state_sha"]
            and facts(r) == facts(a)
            and r["paid"] == a["paid"]
            for r in pair
        )
        w = a["work"]
        wall = [r["cold_wall"] for r in pair]
        covered = a["covered"]
        abst = a["verdicts"]
        row = dict(
            case=case,
            arm=arm,
            steps=steps,
            pages=pages,
            primitive_only=bare,
            fresh_requests=fresh,
            policy_tokens=w.get("final_tokens", 0),
            primitive_receipt_reuses=w.get("neural_primitive_receipt_reuses", 0),
            lowered_suffix=w.get("lowered_suffix", 0),
            covered=covered,
            reference=a["reference"],
            coverage=covered / a["reference"],
            state_sha=a["state_sha"],
            same_terminal_as_A=a["state_sha"] == ref[0]["state_sha"] if ref else "",
            outside_A=len(facts(a) - facts(ref[0])) if ref else "",
            missing_from_A=len(facts(ref[0]) - facts(a)) if ref else "",
            paid=a["paid"],
            effective=a["signed_ops"],
            ept=a["ept"],
            eps=a["signed_ops"] / median(wall),
            wall_median=median(wall),
            wall_min=min(wall),
            wall_max=max(wall),
            accepted=abst.get("accepted", 0),
            duplicate=abst.get("duplicate", 0),
            guard=abst.get("guard", 0),
            watermark=abst.get("watermark", 0),
            version=abst.get("version", 0),
            retired=abst.get("retired", 0),
            draft_end=a.get("draft_end", 0),
            local_end=w.get("unresolved_local_requests", 0),
            waiting=w.get("open_instances", 0),
            named_projections=w.get("owner_projection_reads", 0),
            owner_contracts=w.get("owner_contracts_selected", 0),
            grouped_signed=w.get("optional_entry_paid", 0),
            grouped_accepted=w.get("optional_entry_accepted", 0),
            dense_visits=w.get("visits", 0),
            template_probes=w.get("template_probe", 0),
            port_probes=w.get("port_probe", 0),
            draft_visits=w.get("draft_local_ports_inspected", 0),
            addressing_calls=w.get("address_forward_calls", 0),
            flow_calls=w.get("edit_forward_calls", 0),
            rate_sites=w.get("sites_scored", 0),
            edit_seconds=median(r["work"].get("sampling_seconds", 0) for r in pair),
            selected_higher=w.get("selected_high", 0),
            bound_higher=w.get("instantiated", 0),
            completed_higher=w.get("higher_completed", 0),
        )
        rows.append(row)
    if paths:
        temp = archive.with_suffix(".tmp")
        temp.write_text(
            "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in evidence)
        )
        temp.replace(archive)
    with (out / "frontier.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(len(evidence), "native executions;", len(rows), "paired configurations")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    summarize(p.parse_args().out)
