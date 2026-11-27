"""Replay the exact previous cases and reconcile CCP replies with sampled physical references."""

import copy
import csv
import json
from collections import Counter
from itertools import product

import torch

from cell_kv_runtime import native
from interface_role_train import dest
from interface_role_world import mixed
from partner_index_worlds import args
from selected_cell_study import SEEDS, model, output, reason, store, wrong_mass


def audit(a):
    path = output(a)
    previous = json.loads((dest(a) / "mixed-live.json").read_text())
    prior_mixed = json.loads((dest(a) / "transfer-test-native.json").read_text())
    rows = []
    raw = []
    for seed, checkpoint in product(SEEDS, ("single", "mixed")):
        net = model(a, seed, "legacy", False)
        if checkpoint == "single":
            net.load_state_dict(
                torch.load(dest(a) / f"C-{seed}-1680.pt", weights_only=True)
            )
        counts = Counter()
        risk = []
        for pool, wire, draw in product(range(124081, 124084), (0, 1), (193, 827)):
            local = copy.copy(a)
            local.out = path
            w = mixed(local, net.actor, pool, wire, depth=2)
            log = []
            result = native(a, w, policy=net, seed=draw, receipt_log=log)
            if checkpoint == "single":
                baseline = next(
                    r
                    for r in previous
                    if r["arm"] == "C"
                    and (r["pool"], r["wire"], r["draw"], r["seed"], r["block"])
                    == (pool, wire, draw, seed, 0)
                )
            else:
                baseline = next(
                    r
                    for r in prior_mixed
                    if (
                        r["mode"],
                        r["label"],
                        r["case"],
                        r["wire"],
                        r["draw"],
                        r["seed"],
                        r["block"],
                    )
                    == ("mixed", "mixed", pool, wire, draw, seed, 0)
                )
            assert (
                result["graph"] == baseline["graph"]
                and result["stats"] == baseline["stats"]
                and result["ops"] == baseline["ops"]
            )
            type_count = 0
            for s, decs, replies in log:
                if not s["menu"]:
                    continue
                mass = wrong_mass(net, w, s)
                risk.append(mass)
                issued = []
                for (t, rs), (uid, status, *_) in zip(decs, replies, strict=True):
                    level, idx = reason(w, s, t, rs)
                    issued.append(
                        {
                            "uid": uid,
                            "t": t,
                            "refs": rs,
                            "status": status,
                            "level": level,
                            "parent": idx,
                        }
                    )
                    counts["issued"] += 1
                    counts["version_reject"] += int(status == 8)
                    counts["binding_reject"] += int(status == 9)
                    counts["guard_reject"] += int(status == 12)
                    if status == 7:
                        assert idx is not None
                        counts[level] += 1
                        counts[f"parent_{idx}"] += 1
                        type_count += 1
                    elif level != "compatible":
                        counts["mismatch_with_earlier_verdict"] += 1
                raw.append(
                    {
                        "checkpoint": checkpoint,
                        "seed": seed,
                        "pool": pool,
                        "wire": wire,
                        "draw": draw,
                        "run": s["run"],
                        "epoch": s["epoch"],
                        "risk": mass,
                        "menu": [(t, w.roles[w.layouts[t][0][0]]) for t in s["menu"]],
                        "ports": [(p[0], p[1], p[3]) for p in s["ports"]],
                        "issued": issued,
                    }
                )
            assert result["receipts"]["rejected"].get("type", 0) == type_count
            counts["native_type"] += type_count
            counts["runs"] += 1
        rows.append(
            dict(
                checkpoint=checkpoint,
                seed=seed,
                windows=len(risk),
                mean_incompatible_mass=sum(risk) / len(risk),
                **counts,
            )
        )
    store(path / "historical-audit.json", raw)
    with (path / "historical-audit.csv").open("w") as f:
        keys = list(dict.fromkeys(k for r in rows for k in r))
        wr = csv.DictWriter(f, keys, restval=0, lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)


def arity_choices(a):
    """Disentangle zero-parent generation, admission and contribution on the same root state."""
    from selected_cell_study import world

    rows = []
    for seed, regime in product(SEEDS, (None, "mixed", "curriculum", "diverse")):
        net = model(a, seed, "direct", True, regime)
        for i, draw in product(range(4), (193, 827)):
            w = world(a, net.actor, "arity", i, False)
            log = []
            res = native(a, w, policy=net, seed=draw, receipt_log=log)
            s, _, _ = log[0]
            m = net.state(w, s)
            rec = {
                "seed": seed,
                "regime": regime or "frozen",
                "case": i,
                "draw": draw,
                "graph": res["graph"],
            }
            for name in ("StartMark", "Together"):
                rid = w.outnames[name]
                rec[name + "_root_mass"] = float(
                    m["root_lp"][list(m["families"]).index(rid)].exp()
                )
                statuses = [
                    rep[1]
                    for _, decs, replies in log
                    for (t, rs), rep in zip(decs, replies, strict=True)
                    if t == rid
                ]
                rec[name + "_issued"] = len(statuses)
                rec[name + "_accepted"] = statuses.count(0)
                rec[name + "_facts"] = sum(t == name for t, _ in res["facts"])
            rec["slots"] = sum(6 for s, _, _ in log if s["menu"])
            rec["signed"] = res["stats"]["neural_tokens"]
            rows.append(rec)
    store(output(a) / "arity-choices.json", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        a = args()
        audit(a)
        arity_choices(a)
