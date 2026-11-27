"""Which family receives mass lost by a known triple on the identical native snapshot?"""

import json
import pickle
from collections import defaultdict

import torch

from cell_kv_world import World
from competition_egg import egg
from joint_cell_corpus import folder
from partner_index_worlds import args
from prefix_corpus import folder as old
from prefix_train import CASES, fitted


def run(a):
    rows = []
    for case in CASES:
        ds = pickle.loads((old(a) / f"{case}.pkl").read_bytes())
        known = defaultdict(set)
        for s, r, ts, _ in ds:
            if ts:
                known[s["run"]].add(r)
        nets = {s: fitted(a, case, "rel", s) for s in (0, 71, 113)}
        w = World(egg(a, case)[0], nets[0].actor, entry_table=None, sides="")
        for n in nets.values():
            n.prepare(w)
        for s, r, ts, _ in ds:
            if len(w.roles[r]) != 3 or not ts:
                continue
            p = {}
            for seed, n in nets.items():
                m = n.state(w, s)
                p[seed] = dict(
                    zip(m["families"], m["root_lp"].exp().tolist(), strict=True)
                )
            for seed in (71, 113):
                gains = sorted(
                    ((p[seed][j] - v, j) for j, v in p[0].items() if j != r),
                    reverse=True,
                )
                rows.append(
                    dict(
                        case=case,
                        run=s["run"],
                        rule=r,
                        seed=seed,
                        before=p[0][r],
                        after=p[seed][r],
                        recipients=[
                            dict(rid=j, delta=g, also_verified=j in known[s["run"]])
                            for g, j in gains[:3]
                            if g > 0
                        ],
                    )
                )
    (folder(a) / "root-competition.json").write_text(json.dumps(rows))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
