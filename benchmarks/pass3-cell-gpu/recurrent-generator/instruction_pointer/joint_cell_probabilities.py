"""Per-target probabilities and changes; comparisons never align unrelated targets."""

import json
import math
import os
import pickle
from pathlib import Path

import torch

from cell_kv_world import World
from competition_egg import egg
from joint_cell_corpus import folder
from joint_cell_train import fitted
from partner_index_worlds import args
from prefix_corpus import folder as old


def decomposition(before, after):
    if len(before) != len(after):
        raise ValueError("arity mismatch")
    delta = [y - x for x, y in zip(before, after, strict=True)]
    return dict(
        before=before,
        after=after,
        delta=delta,
        log_before=sum(before),
        log_after=sum(after),
        log_change=sum(delta),
        largest_loss=min(range(len(delta)), key=delta.__getitem__)
        if min(delta) < 0
        else None,
    )


def previous(source):
    rows = {}
    for line in source.read_text().splitlines():
        r = json.loads(line)
        if r["forced"] or r["arm"] != "rel" or r["arity"] != 3:
            continue
        for p in r["probabilities"]:
            logp = list(map(math.log, p["fields"]))
            key = (r["case"], r["run"], r["rid"], tuple(map(tuple, p["refs"])))
            rows.setdefault(key, {})[r["seed"]] = [
                math.log(p["p_token"]) - sum(logp),
                *logp,
            ]
    return [
        dict(
            case=k[0],
            run=k[1],
            rid=k[2],
            refs=k[3],
            arm="previous",
            seed=s,
            **decomposition(ds[0], ds[s]),
        )
        for k, ds in rows.items()
        for s in (71, 113)
    ]


def evaluate(a, case):
    ds = pickle.loads((old(a) / f"{case}.pkl").read_bytes())
    models = {
        (arm, seed): fitted(a, case, arm, seed)
        for arm in ("expanded", "feedback", "small", "replay", "sweep")
        for seed in (0, 71, 113)
    }
    w = World(
        egg(a, case)[0], next(iter(models.values())).actor, entry_table=None, sides=""
    )
    for n in models.values():
        n.prepare(w)
    rows = []
    for s, rid, targets, _ in ds:
        for arm in ("expanded", "feedback", "small", "replay", "sweep"):
            per = {}
            for seed in (0, 71, 113):
                n = models[arm, seed]
                m = n.state(w, s)
                for refs in targets:
                    ix = [m["pos"][r] for r in refs]
                    lp = [float(m["root_lp"][list(m["families"]).index(rid)])]
                    assert len(m["families"][rid]) == 1
                    lp.extend(
                        float(n.address(w, m, rid, ix[:j])[i]) for j, i in enumerate(ix)
                    )
                    assert abs(sum(lp) + float(n.token_loss(w, m, (rid, refs)))) < 1e-4
                    if not seed:
                        per[refs] = lp
                    else:
                        rows.append(
                            dict(
                                case=case,
                                run=s["run"],
                                rid=rid,
                                refs=refs,
                                arm=arm,
                                seed=seed,
                                **decomposition(per[refs], lp),
                            )
                        )
    (folder(a) / f"prob-{case}.json").write_text(json.dumps(rows))


if __name__ == "__main__":
    if os.environ.get("JC_ARCHIVE"):
        print(
            "\n".join(
                json.dumps(r)
                for r in previous(
                    Path("run-recall/prefix-attention/interventions.jsonl")
                )
            )
        )
    else:
        torch.set_num_threads(1)
        with torch.no_grad():
            evaluate(args(), os.environ["TR_CASE"])
