"""Unchanged weights, programmes and published state; vary same-depth catalogue coverage."""

import torch

from competition_results import table
from foundation_fit import model
from foundation_world import data, folder
from partner_index_worlds import args


def run(a):
    root = folder(a)
    rows = []
    for seed in (71, 113):
        n = model(a, seed, 32)
        for small, big in (("half", "short"), ("medium-half", "medium")):
            lhs = data(a, n.actor, small, False, 4)
            rhs = data(a, n.actor, big, False, 4)
            for i, ((left, ls), (right, rs)) in enumerate(zip(lhs, rhs, strict=True)):

                def signature(w, t):
                    tid, refs = t
                    return tuple(
                        (rid, slot, tuple(tuple(x) for x in wires))
                        for rid, slot, wires in w.layouts[tid]
                    ), refs

                l, lp = ls[0]
                r, rp = rs[0]
                assert {k: v for k, v in l.items() if k != "menu"} == {
                    k: v for k, v in r.items() if k != "menu"
                }
                shared = {signature(left, t) for t in lp if t[0] >= left.primitives}
                assert shared and shared <= {signature(right, t) for t in rp}
                for cat, w, s, targets in ((small, left, l, lp), (big, right, r, rp)):
                    n.prepare(w)
                    m = n.state(w, s)
                    p = {t: float((-n.token_loss(w, m, t)).exp()) for t in targets}
                    rows.append(
                        {
                            "seed": seed,
                            "i": i,
                            "arity": len(w.roles[w.root]),
                            "cat": cat,
                            "catalogue": len(w.layouts) - w.primitives,
                            "items": len(s["menu"]),
                            "common": sum(
                                v for t, v in p.items() if signature(w, t) in shared
                            ),
                            "higher": sum(
                                v for t, v in p.items() if t[0] >= w.primitives
                            ),
                            "all_positive": sum(p.values()),
                        }
                    )
    table(root, "catalogue-probe", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
