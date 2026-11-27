"""Independent addressing ablation. Frozen autonomous family and variant selection."""

import json
import os
from pathlib import Path
from time import perf_counter
from types import MethodType

import numpy as np
import torch

from binding_model import tensor
from binding_packets import public_view
from cell_kv_runtime import native
from cell_kv_world import World
from competition_egg import egg
from foundation_egg_catalogue import install
from head_joint_egg import parent_policy
from partner_index_worlds import args, frozen
from query_environment import conditioned
from region_bake import linked
from variable_binding_audit import flat
from variable_completion import CompletionPolicy, directory, network


class SparsePolicy(CompletionPolicy):
    def __init__(self, n, slot_limit, a, d):
        super().__init__(n, False, slot_limit, False)
        self.historical = conditioned(a, d, None)
        self.bind = parent_policy(frozen(a, a.seeds[0]), "joint")
        self.publication_s = 0

    def observe_publication(self, f):
        start = perf_counter()
        flags = [[r, v[0], v[1]] for r, v in f["rule_state"].items()]
        self.historical.update_observed(
            f, (f["run"], f["epoch"], f["check_dirty"], False, flags)
        )
        self.packets = {}
        self.publication_s += perf_counter() - start

    def generate(self, w, s, rng, slots):
        if self.slot_limit is not None:
            slots = min(slots, self.slot_limit - self.count["offered"])
        if not slots:
            return []
        start = perf_counter()
        self.count["offered"] += slots
        self.count["opportunities"] += 1
        cells = []
        if s["menu"]:
            m = self.net.state(w, s)
            self.count["state_encodes"] += 1
            roots = list(m["families"])
            if m["has_complete_domain"]:

                def sample(lp, uniform):
                    mass = lp.double().exp().numpy()
                    return int(
                        np.searchsorted(
                            (mass / mass.sum()).cumsum(), uniform, side="right"
                        )
                    )

                for slot in range(slots):
                    rid = roots[sample(m["root_lp"], rng.random())]
                    # Consume the same root, first-parent, variant and suffix uniforms
                    # as Page.draws. Sparse-only posting noise has its own stream.
                    k = len(w.roles[rid])
                    first = rng.random() if k else None
                    variant_u = rng.random()
                    refs = ()
                    if w.roles[rid]:
                        if rid not in self.packets:
                            visible = {p[0][:2] for p in s["ports"]}
                            self.packets[rid] = public_view(
                                self.historical,
                                w.prog,
                                key=(rid, False),
                                visible=visible,
                            )
                        z = self.packets[rid]
                        u = tensor(
                            np.array([[[first, *rng.random(k - 1)]]], dtype=np.float32)
                        )
                        auxiliary = np.random.default_rng(
                            [193, s["run"], self.count["opportunities"], slot]
                        )
                        ix = self.bind(z, u, auxiliary, self.count)[0, 0].cpu().tolist()
                        refs = tuple(
                            bank[i] for bank, i in zip(z["addrs"], ix, strict=True)
                        )
                    lp = self.net.variant_prob(
                        w, m, rid, m["pos"][refs[0]] if refs else None
                    )
                    tid = m["menu"][m["families"][rid][sample(lp, variant_u)]]
                    cells.append((tid, refs))
        self.count[f"length_{len(cells)}"] += 1
        self.count["signed"] += len(cells)
        self.decode_s += perf_counter() - start
        return cells


def run(a, case):
    ir, align = egg(a, case)
    catalog = json.loads(
        (Path(os.environ["ARTIFACT_ROOT"]) / "region-owner-1126/menu.json").read_text()
    )
    units = linked(json.loads((ir / "program.json").read_text()), catalog)
    d = directory(a)
    matched = os.environ.get("VC_MATCHED") == "1"
    for budget in ("full",) if matched else ("slots", "paid", "full"):
        for rep in (2, 3) if matched else (0, 1):
            for arm in (
                ("KV", "flat", "sparse") if rep % 2 == 0 else ("sparse", "flat", "KV")
            ):
                if matched and arm == "sparse":
                    continue
                suffix = "sparse-paired" if arm == "sparse" else arm
                path = d / f"free-binding-{case}-{budget}-{rep}-{suffix}.json"
                if path.exists():
                    continue
                n = network(a, 71)
                if arm == "flat":

                    def address(self, w, m, tid, pre):
                        if not m["refs"]:
                            return None
                        # Keep the selected Higher's own code for later slots.
                        return flat(self, w, m, tid, pre)

                    n.address = MethodType(address, n)
                w = World(ir, n.actor, entry_table=None, sides="")
                install(w, units, "multi")
                limit = 384 if budget == "slots" else None
                pol = (
                    SparsePolicy(n, limit, a, a.data / case)
                    if arm == "sparse"
                    else CompletionPolicy(n, False, limit, False)
                )
                r = native(
                    a,
                    w,
                    policy=pol,
                    receipt_log=pol,
                    receipt_memory=True,
                    submit_pages=2,
                    slots=6,
                    reference=align,
                    seed=193,
                    paid_limit=96 if budget == "paid" else None,
                    rule_state=True,
                )
                if rep:
                    prior = json.loads(
                        (
                            d / f"free-binding-{case}-{budget}-0-{suffix}.json"
                        ).read_text()
                    )
                    assert all(
                        prior[k] == r[k] for k in ("facts", "graph", "ops", "stats")
                    )
                r.update(
                    case=case,
                    budget=budget,
                    rep=rep,
                    arm=arm,
                    count=pol.count,
                    decode=pol.decode_s,
                    prepare=pol.prepare_s,
                    publication_s=getattr(pol, "publication_s", 0),
                )
                path.write_text(json.dumps(r, separators=(",", ":")))
                print(
                    case, budget, rep, arm, r["covered"], r["stats"]["paid"], flush=True
                )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
