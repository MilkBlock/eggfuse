"""Effect of the logical producer's abstraction on a verified downstream use."""

import torch

from cell_kv_model import CellKV
from cell_kv_runtime import native
from cell_kv_study import checkpoint, names
from cell_kv_world import World
from first_parent import records
from partner_index_worlds import args
from rule_read import load_actor


@torch.no_grad()
def run(a):
    actor = load_actor(a.actor, True)
    held = []
    for name, *_ in names("held"):
        w = World(a.out / "worlds" / name, actor)
        states = native(a, w, teacher="higher")
        held.append((w, states))
    out = []
    for arm in "ABCD":
        for joint in (False, True):
            for seed in (71, 113):
                net = CellKV(a, arm, joint).eval()
                net.load_state_dict(
                    torch.load(checkpoint(a, arm, joint, seed, 360), weights_only=True)
                )
                for w, states in held:
                    net.prepare(w)
                    for state, targets in states:
                        if not any(t in w.finals for t, _ in targets):
                            continue
                        for erase in (False, True):
                            ports = [
                                (
                                    r,
                                    uid,
                                    (w.root if erase and t >= w.primitives else t),
                                    tab,
                                    f,
                                    fw,
                                    refs,
                                )
                                for r, uid, t, tab, f, fw, refs in state["ports"]
                            ]
                            m = net.state(w, dict(state, ports=ports))
                            for t, refs in targets:
                                if t not in w.finals:
                                    continue
                                if not any(
                                    state["ports"][m["pos"][r]][2] >= w.primitives
                                    for r in refs
                                ):
                                    continue
                                out.append(
                                    dict(
                                        case=w.dir.name,
                                        run=state["run"],
                                        arm=arm,
                                        joint=int(joint),
                                        seed=seed,
                                        erase_owner=int(erase),
                                        tid=t,
                                        refs=str(refs),
                                        prob=float(
                                            (-net.token_loss(w, m, (t, refs))).exp()
                                        ),
                                    )
                                )
    records(a.out / "owner.csv", out)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
