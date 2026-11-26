"""Fit existing control logits on the unified experience. Cell address parameters stay frozen."""

import gzip
import json
from collections import Counter, defaultdict

import torch

from discovery_states import save
from execution_control import CONTINUE, SEAL, SUBMIT
from execution_control_data import arguments, fit_actions, supervision


def examples(shard):
    for w in shard["windows"]:
        for act in w["control_events"]:
            credit = act["credit"]
            if "timing" in credit:
                choice = credit["timing"][1]
            elif act["action"] == SUBMIT and (
                "contribution" in credit or "dependency" in credit
            ):
                choice = SUBMIT
            else:
                continue
            if act["mask"][choice] and sum(act["mask"]) > 1:
                yield (
                    act["x"],
                    act["mask"],
                    choice,
                    act["action"] == SEAL and choice == CONTINUE,
                )


def run(a):
    folds = defaultdict(list)
    totals = Counter()
    labels = Counter()
    states = set()
    physical = set()
    signatures = [set(), set()]
    for cohort in ("neural", "shuffle"):
        for idx in range(a.programs):
            with gzip.open(a.out / "ledger" / f"{cohort}-{idx:04d}.json.gz") as inp:
                s = json.load(inp)
            test = idx >= 3 * a.programs // 4
            signatures[test].add(s["signature"])
            new = list(examples(s))
            folds["paired", test].extend(new)
            if test or idx < 12:
                folds["paired-small", test].extend(new)
            folds["raw", test].extend(
                supervision(
                    [
                        {"actions": w["control_events"], "exit": w["exit_audit"]}
                        for w in s["windows"]
                    ]
                )
            )
            totals["program_trajectories"] += 1
            totals["windows"] += len(s["windows"])
            for w in s["windows"]:
                for row in w["control_events"]:
                    states.add(row["state"])
                    totals["control_actions"] += 1
                    for cell in row.get("tokens", []):
                        physical.add((row["state"], json.dumps(cell)))
                        totals["generated_cells"] += 1
                totals["signed_cells"] += len(w["cell_credit"])
                for c in w["cell_credit"]:
                    labels["cell_" + c["reply"]] += 1
                if w["reason"] == "teacher_prefix":
                    totals["teacher_windows"] += 1
            for p in s["pairs"]:
                labels[f"{p['origin']}/{p['target']}"] += 1
                if p["target"] == CONTINUE and p["observed"] == SEAL:
                    labels[f"actual_premature_seal/{p['origin']}"] += 1
                if p.get("delay"):
                    totals["equal_spend_delays"] += 1
                    delta = p["delay"]["delta"]
                    if (
                        delta["same_schedule"]
                        and p["delay"]["credited_ops"] == 0
                        and delta["gained"]
                        and not delta["lost"]
                    ):
                        totals["window_losses"] += 1
            totals["producer_removal_publication_witnesses"] += len(
                s["publication_probes"]
            )
            labels.update(v["prepublication"] for v in s["publication_probes"])
            totals["native_fork_calls"] += s["audit_calls"]
            totals["fork_process_seconds"] += s["audit_wall"]
    if signatures[0] & signatures[1]:
        raise ValueError("structure leakage")
    for kind in ("paired-small", "raw", "paired"):
        fit_actions(a, folds[kind, False], folds[kind, True], "-" + kind)
    save(
        a.out / "inventory.json",
        {
            "totals": totals,
            "counts": labels,
            "distinct_action_states": len(states),
            "distinct_state_named_cells": len(physical),
            "train_signatures": len(signatures[0]),
            "held_signatures": len(signatures[1]),
        },
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(arguments().parse_args())
