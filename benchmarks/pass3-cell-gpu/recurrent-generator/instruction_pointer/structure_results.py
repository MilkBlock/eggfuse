"""Verify paired work counts and derive the reported same-endpoint metrics."""

import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path

from protocol_experiment import dump
from recursive_train import read


def measurements(row):
    w = row["work"]
    structures = row.get("structures", [])
    return {
        "runs": row["runs"],
        "state": row["state_sha"],
        "facts": row["facts"],
        "reference": row["reference"],
        "operations": row["signed_ops"],
        "paid": row["paid"],
        "paid_plus_decisions": row["charged_with_decisions"],
        "ept": row["ept"],
        "ept_including_decisions": row["signed_ops"] / row["charged_with_decisions"],
        "visits": w["visits"],
        "interface_reads": w["interface_reads"],
        "terminal_decisions": row["terminal_decisions"],
        "open_actions": row["open_actions"],
        "reported_suffix_operations": row["new_suffix_operations"],
        "structural_instances": structures,
        "structural_effective_operations_after_root": sum(s["extra_ops"] for s in structures),
        "decisions": {
            k: w.get(k, 0)
            for k in (
                "structure_scores",
                "structure_root_accepted",
                "structure_completed",
                "structure_unavailable_entry",
                "structure_unavailable_return",
                "structure_old",
                "structure_wired_reads",
                "struct_skip_fanout",
                "struct_skip_continuation",
                "open_interface_probes",
                "open_partner_scores",
                "no_watermark_partner",
                "open_contract_choices",
                "open_new_bindings",
                "open_issued_Compose",
                "open_accepted_Compose",
                "open_accepted_Extend",
                "open_reply_Compose_duplicate",
            )
        },
    }


def summarize(store):
    cases = {}
    for case in ("dot", "fact", "loopfact", "sum-divisors"):
        groups = {}
        for arm in ("recent", "pointer", "structure", "rl"):
            rows = [read(store / f"{case}-{arm}-{rep}.json") for rep in range(2)]
            if any(x["termination"] != "schedule_end" for x in rows):
                raise ValueError(f"incomplete {case}/{arm}")
            metrics = measurements(rows[0])
            if measurements(rows[1]) != metrics:
                raise ValueError(f"paired work for {case}/{arm} differs")
            setup_seconds = [read(store / f"{case}-{arm}-setup-{rep}.json")["seconds"] for rep in range(2)]
            groups[arm] = dict(
                metrics,
                wall=[x["wall"] for x in rows],
                eps=[x["eps"] for x in rows],
                setup_seconds=setup_seconds,
                eps_with_separately_measured_setup=[
                    x["signed_ops"] / (x["wall"] + s) for x, s in zip(rows, setup_seconds, strict=True)
                ],
            )
        baseline = groups["recent"]
        for group in groups.values():
            group["same_graph"] = group["state"] == baseline["state"]
            group["paired_wall_delta_seconds"] = [
                t - b for t, b in zip(group["wall"], baseline["wall"], strict=True)
            ]
        cases[case] = groups

    train = [read(store / f"sum-train-{i}-{sign}.json") for i in range(4) for sign in (-1, 1)]
    counts = sum((Counter(x["open_actions"]) for x in train), Counter())
    receipts = Counter()
    for row in train:
        receipts.update(row["new_suffix_operations"])
    return {
        "cases": cases,
        "own_state_partner_audit": {
            case: read(store / f"{case}-probe.json")["partner_audit"]
            for case in ("fact", "loopfact", "sum-divisors")
        },
        "training_actions": counts,
        "training_native_credit": receipts,
        "structure_activations": sum(len(x["structures"]) for x in train),
        "training_completed": sum(x["work"].get("structure_completed", 0) for x in train),
        "input_checksums": {
            f: sha256((store / f).read_bytes()).hexdigest()
            for f in (
                "catalog.json",
                "entry-contracts.json",
                "wired.pt",
                "graph.pt",
                "recursive-rl.pt",
                "structure-book.json",
                "structure-rl.pt",
            )
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("store", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    dump(a.out, summarize(a.store))
