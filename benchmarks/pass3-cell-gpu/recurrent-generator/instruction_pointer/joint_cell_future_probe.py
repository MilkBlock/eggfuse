"""Disable only future-role messages at identical trained weights, on real three-parent targets."""

import json
import pickle

import torch

from cell_kv_world import World
from competition_egg import egg
from joint_cell_corpus import folder
from joint_cell_train import CASES, fitted
from partner_index_worlds import args
from prefix_corpus import folder as old


def probe(a):
    all_rows = []
    for case in CASES:
        for seed in (71, 113):
            on = fitted(a, case, "feedback", seed)
            off = fitted(a, case, "expanded", 0)
            off.load_state_dict(on.state_dict())
            on.audit_future = True
            w = World(egg(a, case)[0], on.actor, entry_table=None, sides="")
            on.prepare(w)
            off.prepare(w)
            rows = pickle.loads((old(a) / f"{case}.pkl").read_bytes())
            for s, rid, ts, _ in rows:
                if len(w.roles[rid]) != 3:
                    continue
                for refs in ts:
                    active = on.state(w, s)
                    loss = on.token_loss(w, active, (rid, refs))
                    probes = active.get("future_probes", [])
                    grad = (
                        torch.autograd.grad(loss, [v[2] for v in probes])
                        if probes
                        else []
                    )
                    with torch.no_grad():
                        disabled = off.state(w, s)
                        bare = off.token_loss(w, disabled, (rid, refs))
                    all_rows.append(
                        dict(
                            case=case,
                            run=s["run"],
                            rid=rid,
                            refs=refs,
                            seed=seed,
                            delta_logp=float((bare - loss).detach()),
                            gradient=[
                                [j, k, float(v.norm())]
                                for (j, k, _), v in zip(probes, grad, strict=True)
                            ],
                        )
                    )
    (folder(a) / "future-probes.json").write_text(json.dumps(all_rows))


if __name__ == "__main__":
    torch.set_num_threads(1)
    probe(args())
