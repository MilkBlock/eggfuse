"""Frozen addressing ablation on the native CCP stream, with a common Recipe draw."""

import os
from collections import Counter

import numpy as np
import torch

from binding_egg import execute
from completion_context import read
from foundation_completion import Choice, Completion, Decision
from foundation_diagnostics import Interface
from foundation_study import BASE, CASES
from head_joint_egg import parent_policy
from multirule_higher import trial
from multirule_support import chooser
from partner_index_worlds import args, frozen
from recursive_coverage import Target
from recursive_train import folder
from shared_posting import SparseCompletion


class CommonPage:
    def __init__(self, model, arm):
        self.arm = arm
        self.dec = (
            SparseCompletion(model, anchor=arm == "C-anchor")
            if arm.startswith("C")
            else Completion(model, "rule")
        )
        if arm == "Bcompact":
            self.dec.mem.compact = True

    def publish(self, m, prog, frame, stats):
        self.dec.publish(m, prog, frame, stats)

    def generate(self, m, slots, rng, stats):
        d = self.dec
        u = rng.random((slots, max(1, (len(m.ids) - 1).bit_length()))).astype(
            np.float32
        )
        p = Choice(d.ctx, d.rkeys, d.ctx.new_zeros(len(d.ids)), 0).logp(d.net).exp()
        selected = torch.searchsorted(
            p.cumsum(0), torch.from_numpy(u[:, 0].copy()).to(d.device)
        ).clamp_max(len(d.ids) - 1)
        templates = [d.ids[i] for i in selected.cpu().tolist()]
        cells = [None] * slots
        for rid in dict.fromkeys(templates):
            group = [i for i, r in enumerate(templates) if r == rid]
            if self.arm.startswith("C"):
                batch = d.bind(rid, len(group), rng, stats)
            else:
                batch = [
                    d.finish(Decision(d.net, rng, stats), fixed_rule=rid, stats=stats)[
                        1
                    ]
                    for _ in group
                ]
            for i, c in zip(group, batch, strict=True):
                cells[i] = c
        self.events = [{} for _ in cells]
        return templates, cells


@torch.no_grad()
def live(a):
    a.slots = int(os.environ.get("PAGE_SLOTS", "8"))
    arms = os.environ.get("ARMS", "A,B,Bcompact,C").split(",")
    for case in os.environ.get("CASES", ",".join(CASES)).split(","):
        d = folder(a.data, case)
        rt = a.out / case
        rt.mkdir(exist_ok=True)
        target = Target(read(d / "program.json"), read(BASE / case / "ref.json"))
        ref = target, target.match(read(BASE / case / "init.json"))
        model = frozen(a, a.seeds[0])
        model.load_state_dict(
            torch.load(BASE / f"{case}-ce-count.pt", weights_only=True)
        )
        for seed in map(int, os.environ.get("DRAWS", "9734,9805").split(",")):
            for block in range(int(os.environ.get("BLOCKS", "2"))):
                for arm in arms if block % 2 == 0 else arms[::-1]:
                    dest = rt / f"{arm}-{seed}-{block}"
                    if a.slots != 8:
                        dest = dest.with_name(f"page{a.slots}-" + dest.name)
                    if (dest / "result.json").exists():
                        continue
                    policies = (
                        {"page_policy": CommonPage(model, arm)}
                        if arm != "A"
                        else {
                            "parent_policy": parent_policy(model, "joint"),
                            "template_policy": chooser(model, "ce-count"),
                        }
                    )
                    execute(
                        a,
                        d,
                        dest,
                        model.local.base,
                        arm,
                        9633,
                        block,
                        seed,
                        ref,
                        address_seed=179636 + seed - 9734,
                        **policies,
                    )
                    r = read(dest / "result.json")
                    print(
                        case,
                        arm,
                        seed,
                        block,
                        r["covered"],
                        r["ops"],
                        r["wall"],
                        flush=True,
                    )


class HigherInterface(Interface):
    """Given-template control with identical tensor accounting for all three arms."""

    def __init__(self, model, arm):
        self.arm = arm
        self.model = model
        self.dec = SparseCompletion(model) if arm == "C" else Completion(model, "rule")
        self.cost = 0.0

    def publish(self, m, prog, frame):
        self.memory = m
        self.prog = prog
        if self.arm != "A":
            super().publish(m, prog, frame)

    def bind(self, rid, code):
        from binding_packets import public_view
        from discrete_draft import Cell
        from head_joint_index import prepare, draw
        from partner_index import noise
        from selective_trials import inputs
        from shared_posting_cost import storage, timed

        d = self.dec
        rng = np.random.default_rng(419)
        if self.arm == "A":

            def build():
                z = public_view(self.memory, self.prog, key=(rid, False))
                data = inputs(z, False)
                return z, data, prepare(self.model, data)

            (z, data, state), build_ms = timed(build)
            feats = data[0][3]
            idx = [e.index for e in state[1]]
            cache = [state[0], [(e.start, e.count, e.mass) for e in state[1]]]
            recipe = (data[0][:3], data[1])

            def sample():
                picks = draw(data, state, noise(rng, 32, 2))[0].cpu().tolist()
                return [
                    Cell(rid, tuple(z["addrs"][j][v] for j, v in enumerate(rr)))
                    for rr in picks
                ]
        else:
            build_ms = self.cost * 1000
            d.rkeys[d.rpos[rid]] = code.to(d.device)
            recipe = (d.schemas, d.rkeys, d.ctx)
            if self.arm == "C":
                feats = [(b.keys, b.lo, b.frac) for b in d.mem.banks.values()]
                idx = [
                    (b.offsets, b.starts, b.ends, b.owners)
                    for b in d.mem.banks.values()
                ]
                cache = []

                def sample():
                    return d.bind(rid, 32, rng, Counter())
            else:
                feats = [(b.keys, b.fields) for b in d.mem.pages.values()] + [
                    (v[2], v[3]) for v in d.mem.rows.values()
                ]
                idx = [b.mean for b in d.mem.pages.values()]
                cache = d.coarse

                def sample():
                    return [
                        d.finish(Decision(d.net, rng, Counter()), fixed_rule=rid)[1]
                        for _ in range(32)
                    ]

        cells, ms = timed(sample)
        seen = set()
        self.sizes = {
            label: storage(obj, seen)
            for label, obj in (
                ("features_B", feats),
                ("index_B", idx),
                ("cache_B", cache),
                ("recipe_B", recipe),
            )
        }
        return cells, self.sizes["index_B"], build_ms, ms


@torch.no_grad()
def higher(a):
    from first_parent import records

    (a.out / "higher").mkdir(exist_ok=True)
    model = frozen(a, a.seeds[0])
    rows = []
    for n in (6, 32, 128, 256):
        d = folder(BASE / "higher/data", f"scale-fork-{n}-2-17-jobs8")
        for block in range(2):
            for arm in ("A", "B", "C") if block == 0 else ("C", "B", "A"):
                interface = HigherInterface(model, arm)
                result = trial(a, d, model, block, interface)
                rows.append(dict(arm=arm, **result, **interface.sizes))
        records(a.out / "higher.csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    {"live": live, "evaluate": higher}[a.task](a)
