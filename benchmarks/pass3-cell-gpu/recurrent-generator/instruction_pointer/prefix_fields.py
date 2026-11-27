"""Offline field-level score interventions; edited views never drive execution."""

import json
import os
import pickle

import torch

from cell_kv_world import World
from competition_egg import egg
from partner_index_worlds import args
from prefix_attention import static_wires
from prefix_corpus import folder
from prefix_train import fitted


def run(a, case):
    d = folder(a)
    ir, _ = egg(a, case)
    rows = []
    grads = []
    for arm, seed in [("base", 0), ("rel", 0), ("base", 71), ("rel", 71), ("rel", 113)]:
        n = fitted(a, case, arm, seed)
        w = World(ir, n.actor, entry_table=None, sides="")
        n.prepare(w)
        for s, rid, gold, _ in pickle.loads((d / f"{case}.pkl").read_bytes()):
            if not gold or len(w.roles[rid]) < 2:
                continue
            if arm == "rel":
                n.probe_relation = True
                with torch.enable_grad():
                    m = n.state(w, s)
                    loss = n.token_loss(w, m, (rid, gold[0]))
                    selected = m.get("probe_tensors", [])
                    if selected:
                        q, k, vb, vc = selected[-1]
                        gradient = torch.autograd.grad(loss, (q, k, vb, vc))
                        grads.append(
                            {
                                "case": case,
                                "seed": seed,
                                "run": s["run"],
                                "rid": rid,
                                "ce": float(loss.detach()),
                                "norms": [float(p.norm()) for p in gradient],
                            }
                        )
                n.probe_relation = False
            ports = s["ports"]
            m = n.state(w, s)
            seen = set()
            for refs in gold:
                indices = [m["pos"][ref] for ref in refs]
                i = indices[0]
                b = indices[1]
                links = static_wires(w, rid, 1)
                for _, src, col, _ in links:
                    if (i, src) in seen or i == b:
                        continue
                    other = next(
                        (
                            h
                            for h, p in enumerate(ports)
                            if h not in (i, b)
                            and p[3] == ports[b][3]
                            and p[4][col] != ports[b][4][col]
                            and all(
                                p[4][c] == ports[b][4][c]
                                for _, ss, c, _ in links
                                if ss != src
                            )
                        ),
                        None,
                    )
                    if other is None:
                        continue
                    seen.add((i, src))
                    lp = n.address(w, m, rid, (i,))
                    initial = float(lp[b] - lp[other])
                    for purpose, at in [
                        ("wired", src),
                        (
                            "unwired",
                            next(
                                (
                                    k
                                    for k in range(len(ports[i][4]))
                                    if k not in {x[1] for x in links}
                                ),
                                None,
                            ),
                        ),
                    ]:
                        if at is None:
                            continue
                        row = list(ports[i])
                        fields = list(row[4])
                        fields[at] = ports[other][4][col]
                        row[4] = tuple(fields)
                        edited = list(ports)
                        edited[i] = tuple(row)
                        nm = n.state(w, dict(s, ports=edited))
                        pp = n.address(w, nm, rid, (i,))
                        rows.append(
                            {
                                "case": case,
                                "run": s["run"],
                                "rid": rid,
                                "arm": arm,
                                "seed": seed,
                                "kind": purpose,
                                "source": refs[0],
                                "target": refs[1],
                                "foil": ports[other][0],
                                "src": at,
                                "col": col,
                                "before": initial,
                                "after": float(pp[b] - pp[other]),
                            }
                        )
    (d / f"probe-results-{case}.json").write_text(
        json.dumps({"swaps": rows, "gradients": grads})
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
