"""Matched page allocation supervision trains only the existing editable action logits."""

from collections import Counter

import torch

from control_credit_experience import load, records
from discovery_states import read, save
from execution_control import CONTINUE, SEAL, SUBMIT
from execution_control_data import arguments, fit_actions


def train(a):
    folds = [[], []]
    sigs = [set(), set()]
    count = Counter()
    reports = []
    for c in ("neural", "shuffle"):
        for idx in range(a.programs):
            name = f"{c}-{idx:04d}.json.gz"
            sh = load(a.out, "ledger", name)
            comp = load(a.out, "allocation", name)
            split = int(idx >= 3 * a.programs // 4)
            sigs[split].add(sh["signature"])
            live = read(a.out / "live" / f"{idx}.json") if a.use_live else []
            for r in records(sh, comp, live):
                count[r["kind"]] += 1
                if r["kind"] == "cell":
                    continue
                cred = r["credit"]
                axis = next(
                    (
                        k
                        for k in ("live_allocation", "allocation", "timing")
                        if k in cred
                    ),
                    None,
                )
                if axis:
                    choice = cred[axis][1]
                elif r["action"] == SUBMIT and "contribution" in cred:
                    choice = SUBMIT
                else:
                    continue
                if sum(r["mask"]) > 1 and r["mask"][choice]:
                    folds[split].append(
                        (
                            r["x"],
                            r["mask"],
                            choice,
                            r["action"] == SEAL and choice == CONTINUE,
                        )
                    )
            for v in comp["records"]:
                count["equal_page_pairs"] += 1
                count["equal_page_paid_each"] += v["paid_each"]
                count["equal_page_" + str(v["target"])] += 1
                count["equal_page_unaccounted"] += int(not v["receipts_accounted"])
                if len([x for x in reports if x["target"] == v["target"]]) < 3:
                    reports.append(dict(program=idx, cohort=c, **v))
            for v in comp["delays"]:
                count["delay_unaccounted"] += int(not v["accounted"])
                count.update({"delayed_" + k: n for k, n in v["verdicts"].items()})
    if sigs[0] & sigs[1]:
        raise ValueError("structure leakage")
    fit_actions(a, *folds, "-" + a.label)
    if not a.use_live:
        save(a.out / "allocation-inventory.json", count)
    save(a.out / "allocation-examples.json", reports)


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--use-live", action="store_true")
    p.add_argument("--label", default="matched")
    torch.set_num_threads(1)
    train(p.parse_args())
