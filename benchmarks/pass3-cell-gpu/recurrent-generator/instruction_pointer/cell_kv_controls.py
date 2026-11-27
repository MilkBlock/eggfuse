"""Reuse both published sparse address implementations under the identical mixed template menu."""

from collections import Counter, defaultdict
from types import SimpleNamespace

import numpy as np
import torch

from binding_packets import public_view
from cell_kv_model import CellKV
from cell_kv_runtime import native
from cell_kv_study import checkpoint, names
from cell_kv_world import World
from head_joint_egg import parent_policy
from partner_index_worlds import args, frozen
from shared_posting import SparseCompletion
from first_parent import records


class SparseControl:
    def __init__(self, a, base, kind):
        self.base = base
        self.legacy = frozen(a, a.seeds[0])
        self.kind = kind
        self.bind = parent_policy(self.legacy, "joint")

    def prepare(self, w):
        self.base.prepare(w)
        self.previous = {}
        self.shared = SparseCompletion(self.legacy, "mps", anchor=True)
        self.stats = Counter()

    def generate(self, w, state, rng, slots):
        if not state["menu"] or not state["ports"]:
            return []
        base = self.base
        m = base.state(w, state)
        nodes, codes, _ = base.cache
        visible = {}
        rows = defaultdict(list)
        current = {}
        updates = []
        for i, (ref, _, _, table, fields, fwd, _) in enumerate(state["ports"]):
            key = ref[:2]
            rec = dict(table=table, version=ref[2], hashes=fields, forwarded=fwd)
            visible[key] = rec, m["ext"][i]
            rows[table].append(key)
            current[key] = ref[2]
            if self.previous.get(key) != ref[2]:
                updates.append((dict(token=ref[0], op=ref[1]), rec))
        api = SimpleNamespace(
            pub=SimpleNamespace(live=visible),
            rows=rows,
            last=None,
            roles=w.roles,
            ids=[(r, False) for r in state["menu"] if r < w.primitives],
            enc=SimpleNamespace(nodes=nodes, cat=w.cat),
            context=lambda: m["ctx"],
            graph=lambda key: codes[key[0]],
            key=lambda k: visible[k][1],
        )
        if self.kind == "shared":
            self.shared.publish(
                api,
                w.prog,
                dict(
                    updates=updates,
                    retired=[
                        dict(token=k[0], op=k[1])
                        for k in self.previous.keys() - current.keys()
                    ],
                ),
                self.stats,
            )
        self.previous = current
        positions = np.searchsorted(
            m["lp"].exp().cumsum(0).numpy(), rng.random(slots)
        ).clip(max=len(state["menu"]) - 1)
        templates = [state["menu"][i] for i in positions]
        out = [None] * slots
        for tid in dict.fromkeys(templates):
            group = [i for i, t in enumerate(templates) if t == tid]
            rid = w.layouts[tid][0][0]
            if self.kind == "shared":
                self.shared.rkeys[self.shared.rpos[rid]] = codes[tid].to("mps")
                batch = self.shared.bind(rid, len(group), rng, self.stats)
                bound = [None if c is None else c.refs for c in batch]
            else:
                z = public_view(api, w.prog, key=(rid, False))
                if any(not b for b in z["addrs"]):
                    continue
                u = torch.from_numpy(
                    rng.random((1, len(group), len(z["banks"])), dtype=np.float32)
                ).to("mps")
                picks = self.bind(z, u, rng, self.stats)[0].cpu().tolist()
                bound = [
                    tuple(z["addrs"][j][i] for j, i in enumerate(p)) for p in picks
                ]
            for i, refs in zip(group, bound, strict=True):
                if refs is not None:
                    out[i] = tid, refs
        return [c for c in out if c is not None]


@torch.no_grad()
def run(a):
    rows = []
    for seed in (71, 113):
        net = CellKV(a, "A", True).eval()
        net.load_state_dict(
            torch.load(checkpoint(a, "A", True, seed, 360), weights_only=True)
        )
        for name, *_ in names("held"):
            w = World(a.out / "worlds" / name, net.actor)
            for draw in (193, 827):
                for block in (0, 1):
                    for kind in (
                        ("joint", "shared") if not block else ("shared", "joint")
                    ):
                        ctl = SparseControl(a, net, kind)
                        r = native(a, w, policy=ctl, seed=draw)
                        rows.append(
                            dict(
                                case=name,
                                seed=seed,
                                draw=draw,
                                block=block,
                                kind=kind,
                                coverage=r["coverage"],
                                covered=r["covered"],
                                graph=r["graph"],
                                paid=r["stats"]["paid"],
                                ops=r["ops"],
                                ept=r["ept"],
                                eps=r["eps"],
                                wall=r["wall"],
                                selected=r["stats"].get("higher_selected", 0),
                                opened=r["stats"].get("higher_opened", 0),
                                confirmed=r["stats"]["higher_completed"],
                            )
                        )
            records(a.out / "legacy.csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
