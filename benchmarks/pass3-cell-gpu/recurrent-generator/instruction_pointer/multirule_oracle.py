"""Offline correct-rule intervention at exact autonomous publications."""

import json
import os
from collections import Counter

import numpy as np
import torch

from binding_model import tensor
from binding_packets import public_view
from completion_context import native, read, write
from discrete_cells import from_q
from first_parent import records
from head_joint_egg import parent_policy
from partner_index_worlds import args, frozen
from query_environment import conditioned
from recursive_train import folder


def fork(a, d, path, tape, base, run, cells, *, export=None):
    start = max((q["token"] for q in base), default=0) + 1
    req = [
        {
            "token": start + j,
            "run": run,
            "rule": c.rule,
            "parents": [
                {"address": {"token": t, "op": o}, "version": v} for t, o, v in c.refs
            ],
        }
        for j, c in enumerate(cells)
    ]
    write(path, dict(tape, requests=base + req))
    rep = native(a, d, "replay", path, run, *(("--export", export) if export is not None else ()), "--ept-origins")
    orig = dict(rep["ept"]["origins"])
    receipts = rep["counts"]
    verdict = {
        "accepted": receipts["accepted"] - len(base),
        "duplicates": receipts["duplicates"],
        "binding": receipts["rejected"].get("binding", 0),
        "guard": receipts["rejected"].get("guard", 0),
        "other_rejects": sum(
            v for k, v in receipts["rejected"].items() if k not in ("binding", "guard")
        ),
    }
    assert sum(verdict.values()) == len(cells) and all(v >= 0 for v in verdict.values())
    return [orig.get(q["token"], 0) for q in req], verdict


@torch.no_grad()
def run(a):
    model = frozen(a, a.seeds[0])
    bind = parent_policy(model, "joint")
    results = []
    inventory = []
    for case in ("sum-divisors", "fact", "loopfact"):
        d = folder(a.data, case)
        prog = read(d / "program.json")
        src = a.out / case / "audit-0"
        work = a.out / "forks" / case
        work.mkdir(parents=True, exist_ok=True)
        tape = read(src / "accepted.json")
        raw = read(src / "slots.json")
        allruns = sorted({r["run"] for r in raw})
        # Uniform temporal checkpoints plus starts and productive windows; report strata.
        good = {r["run"] for r in raw if r["gain"] > 0}
        selected = (
            set(allruns[:10])
            | set(np.random.default_rng(230).choice(allruns, 24, replace=False))
            | good
        )
        replay = native(
            a,
            d,
            "replay",
            src / "accepted.json",
            "--memory",
            work / "frames",
            "--ept-origins",
            env=dict(os.environ, EGGFUSE_QUERY_OBSERVER=str(work / "observer")),
        )
        assert replay["state_sha"] == read(src / "result.json")["graph"]
        m = conditioned(a, d, work / "observer")
        try:
            for line in (work / "frames").open():
                f = json.loads(line)
                if f.get("final_publication"):
                    continue
                m.update(f)
                r = f["run"]
                if r not in selected:
                    continue
                prefix = [q for q in tape["requests"] if q["run"] < r]
                exact = native(
                    a, d, "replay", src / "accepted.json", r - 1, "--audit-next-proofs"
                )
                rng = np.random.default_rng([113, r])
                rng.shuffle(exact)
                # Sample a bounded witness set and obtain native origin credit before supplying ANY rule.
                gold = [from_q(q) for q in exact[:48]]
                gains, _ = fork(a, d, work / "probe.json", tape, prefix, r, gold)
                rules = sorted(
                    {c.rule for c, g in zip(gold, gains, strict=True) if g > 0}
                )
                inventory.append(
                    {
                        "case": case,
                        "run": r,
                        "positive_window": r in good,
                        "exact": len(exact),
                        "verified": len(gold),
                        "positive_rules": len(rules),
                    }
                )
                for rid in rules[:4]:
                    z = public_view(m, prog, key=(rid, False)) if m.roles[rid] else None
                    from discrete_draft import Cell

                    if z:
                        k = len(z["banks"])
                        u = tensor(rng.random((1, 8, k), dtype=np.float32))
                        ix = bind(z, u, rng, Counter())[0].cpu().tolist()
                        cells = [
                            Cell(
                                rid,
                                tuple(
                                    b[p] for b, p in zip(z["addrs"], row, strict=True)
                                ),
                            )
                            for row in ix
                        ]
                    else:
                        cells = [Cell(rid, ())] * 8
                    ys, verdict = fork(
                        a, d, work / "probe.json", tape, prefix, r, cells
                    )
                    results.append(
                        dict(
                            case=case,
                            run=r,
                            rule=rid,
                            arity=len(cells[0].refs),
                            slots=len(ys),
                            productive=sum(v > 0 for v in ys),
                            ops=sum(ys),
                            **verdict,
                        )
                    )
        finally:
            m.close_observer()
        records(a.out / "oracle.csv", results)
        records(a.out / "checkpoints.csv", inventory)
        print(case, len(inventory), len(results), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
