"""Paired offline interventions. Runtime exports establish distinct additional facts."""

import json
import os
import pickle
from pathlib import Path

import numpy as np
import torch

from binding_model import collate, tensor
from cell_kv_world import World
from competition_egg import egg
from discrete_draft import Cell
from head_joint_index import prepare
from multirule_oracle import fork
from partner_index import EXPLORE, categorical, noise
from partner_index_worlds import args, frozen
from prefix_corpus import folder
from prefix_train import fitted
from selective_kernel import pack, role_tree


class Historical:
    def __init__(self, model, z):
        self.model = model
        self.z = dict(z, banks=[dict(b, last=-1) for b in z["banks"]])
        self.data = None
        if len(z["banks"]) > 1:
            try:
                role_tree(z["slots"])
            except ValueError as e:
                if str(e) != "requires exactly one earlier connected role per child":
                    raise
            else:
                self.data = pack([self.z])
                self.p, self.edges = prepare(model, self.data)
        self.inp = collate([self.z])

    def draw(self, u, rng, forced):
        u = tensor(u)
        if self.data:
            v = noise(rng, u.shape[1], u.shape[2])
            v[:, :, :, 0, 0] = u
            refs = [
                categorical(self.p, v[:, :, 0, 0, 0])
                if forced is None
                else tensor(forced[None])
            ]
            for j, (par, _) in enumerate(self.data[1], 1):
                refs.append(self.edges[j - 1].draw(refs[par], v[:, :, j, 0]))
            return torch.stack(refs, -1)[0].cpu().tolist()
        if forced is None:
            return (
                self.model.local.base(self.inp, draws=u.shape[1], noise=u)[1][0]
                .cpu()
                .tolist()
            )
        teacher = torch.zeros_like(u, dtype=torch.long)
        teacher[:, :, 0] = tensor(forced[None])
        for j in range(1, u.shape[2]):
            lp = self.model.local.base(self.inp, teacher=teacher)[0][j]
            teacher[:, :, j] = (
                (lp.exp().cumsum(-1) < u[:, :, j, None])
                .sum(-1)
                .clamp_max(lp.shape[-1] - 1)
            )
        return teacher[0].cpu().tolist()

    def masses(self, ix):
        if self.data is None:
            lp, _ = self.model.local.base(
                self.inp, teacher=tensor(np.array([[ix]], dtype=np.int64))
            )
            return [float(v[0, 0, i].exp()) for v, i in zip(lp, ix, strict=True)]
        probs = [float(self.p[0, ix[0]])]
        for j, (par, _) in enumerate(self.data[1], 1):
            e = self.edges[j - 1]
            root = ix[par]
            n = len(self.z["addrs"][j])
            weights = e.mass[0, root].cpu().double()
            if weights.sum() == 0:
                probs.append(1 / n)
                continue
            ends = e.index.ends[0].cpu()
            hit = e.index.owners[0].cpu() == ix[j]
            lo, hi = ends[:-1][hit], ends[1:][hit]
            local = []
            for start, count in zip(
                e.start[0, root].cpu(), e.count[0, root].cpu(), strict=True
            ):
                overlap = (
                    (torch.minimum(hi, start + count) - torch.maximum(lo, start))
                    .clamp_min(0)
                    .sum()
                )
                local.append(float(overlap / count) if count else 0.0)
            probs.append(
                EXPLORE / n
                + (1 - EXPLORE)
                * float(weights @ weights.new_tensor(local) / weights.sum())
            )
        return probs


def run(a, case):
    d = folder(a)
    ir, align = egg(a, case)
    archive = Path(os.environ["ARTIFACT_ROOT"]) / "multi-association" / case / "audit-0"
    tape = json.loads((archive / "accepted.json").read_text())
    ds = pickle.loads((d / f"{case}.pkl").read_bytes())
    past = frozen(a, a.seeds[0])
    rows = []
    arms = [
        ("base", 0),
        ("sparse", 0),
        ("rel", 0),
        ("base", 71),
        ("rel", 71),
        ("base", 113),
        ("rel", 113),
        ("rel_off", 71),
    ]
    nets = {(arm, seed): fitted(a, case, arm, seed) for arm, seed in arms}
    w = World(ir, nets["base", 0].actor, entry_table=None, sides="")
    for n in nets.values():
        n.prepare(w)
    for s, rid, gold, z in ds:
        r = s["run"]
        arity = len(w.roles[rid])
        banks = z["addrs"]
        historical = Historical(past, z)
        prefix = [q for q in tape["requests"] if q["run"] < r]

        def replay(cells, prefix=prefix, r=r):
            export = d / f"branch-{case}.json"
            gains, verdict = fork(
                a,
                a.data / case,
                d / f"decisions-{case}.json",
                tape,
                prefix,
                r,
                cells,
                export=export,
            )
            return gains, verdict, align(json.loads(export.read_text()))[0]

        _, _, baseline = replay([])
        starts = list(dict.fromkeys(refs[0] for refs in gold))
        for arm, seed in arms:
            n = nets[arm, seed]
            m = n.state(w, s)

            def conditional(pre, n=n, m=m, rid=rid):
                return n.address(w, m, rid, pre).double().exp().numpy()

            root = float(m["root_lp"][list(m["families"]).index(rid)].exp())
            ps = []
            for refs in gold:
                ids = tuple(m["pos"][ref] for ref in refs)
                if arm == "sparse":
                    mass = historical.masses(
                        [b.index(ref) for b, ref in zip(banks, refs, strict=True)]
                    )
                else:
                    mass = [float(conditional(ids[:j])[i]) for j, i in enumerate(ids)]
                vp = n.variant_prob(w, m, rid, ids[0])[
                    m["families"][rid].index(m["menu"].index(rid))
                ].exp()
                ps.append(
                    {
                        "refs": refs,
                        "fields": mass,
                        "p_token": root * float(vp) * np.prod(mass),
                    }
                )
            for forced in (False, True) if starts and arity > 1 else (False,):
                rng = np.random.default_rng([113, r, rid])
                u = rng.random((1, 16, arity), dtype=np.float32)
                selected = (
                    [starts[i % len(starts)] for i in range(16)] if forced else []
                )
                if arm == "sparse":
                    ids = historical.draw(
                        u,
                        rng,
                        np.array([banks[0].index(ref) for ref in selected])
                        if forced
                        else None,
                    )
                    cells = [
                        Cell(rid, tuple(b[i] for b, i in zip(banks, row, strict=True)))
                        for row in ids
                    ]
                else:
                    cells = []
                    memo = {}
                    for k, v in enumerate(u[0]):
                        pre = (m["pos"][selected[k]],) if forced else ()
                        for t in v[len(pre) :]:
                            if pre not in memo:
                                p = conditional(pre)
                                memo[pre] = (p / p.sum()).cumsum()
                            pre += (int(memo[pre].searchsorted(t, side="right")),)
                        cells.append(Cell(rid, tuple(m["refs"][i] for i in pre)))
                gain, verdict, facts = replay(cells)
                rows.append(
                    dict(
                        case=case,
                        run=r,
                        rid=rid,
                        arity=arity,
                        arm=arm,
                        seed=seed,
                        forced=forced,
                        index=historical.data is not None,
                        probabilities=ps,
                        paid=16,
                        productive=sum(v > 0 for v in gain),
                        ops=sum(gain),
                        new_facts=sorted(facts - baseline),
                        lost_facts=sorted(baseline - facts),
                        **verdict,
                    )
                )
    (d / f"audit-{case}.json").write_text(json.dumps(rows, separators=(",", ":")))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
