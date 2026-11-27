"""Training-state diagnosis of complete-token CE; no probe is fitted or used online."""

import torch

from cell_kv_model import CellKV
from cell_kv_study import checkpoint, names
from cell_kv_world import World
from first_parent import records
from partner_index_worlds import args


@torch.no_grad()
def run(a):
    data = torch.load(a.out / "training.pt", weights_only=False)
    rows = []
    for arm in "BCD":
        for joint, steps in ((False, 0), (False, 360), (True, 360)):
            for seed in (71, 113):
                net = CellKV(a, arm, joint).eval()
                if steps:
                    net.load_state_dict(
                        torch.load(
                            checkpoint(a, arm, joint, seed, steps), weights_only=True
                        )
                    )
                for name, depth, jobs, _ in names("train"):
                    w = World(a.out / "worlds" / name, net.actor)
                    net.prepare(w)
                    state, targets = data[name][0]
                    m = net.state(w, state)
                    for gold, refs in targets:
                        if gold < w.primitives:
                            continue
                        other = 2 * w.primitives + 1 - gold
                        p, r = [
                            m["lp"][m["menu"].index(t)].exp() for t in (gold, other)
                        ]
                        bp, br = [
                            net.address(w, m, t, []).exp()[m["pos"][refs[0]]]
                            for t in (gold, other)
                        ]
                        more = {x[0]: x for x in state["ports"]}
                        fields = more[refs[0]][4]
                        assert (fields[0] == fields[1]) == (gold == w.primitives)
                        rows.append(
                            dict(
                                arm=arm,
                                joint=int(joint),
                                updates=steps,
                                seed=seed,
                                name=name,
                                depth=depth,
                                jobs=jobs,
                                given_h=float(bp),
                                relative_h=float(p / (p + r)),
                                relative_complete=float(p * bp / (p * bp + r * br)),
                            )
                        )
    records(a.out / "fit.csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
