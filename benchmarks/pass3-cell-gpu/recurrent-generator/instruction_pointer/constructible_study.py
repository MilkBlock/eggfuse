"""Frozen type-support ablations, including signed-response and empty-slot accounting."""

import json
import os
from collections import Counter
from time import perf_counter

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from cell_transaction import STATUS
from competition_draw import Page
from competition_egg import egg
from feedback_train import get
from partner_index_worlds import args


def directory(a):
    p = a.out / "constructible"
    p.mkdir(exist_ok=True)
    return p


class TracePolicy:
    def __init__(self, net, unique, slot_limit=None):
        self.net = net
        self.unique = unique
        self.slot_limit = slot_limit
        self.count = Counter()
        self.pages = []
        self.decode_s = 0.0

    def prepare(self, w):
        t = perf_counter()
        self.net.prepare(w)
        self.prepare_s = perf_counter() - t

    def generate(self, w, s, rng, slots):
        start = perf_counter()
        if self.slot_limit is not None:
            slots = min(slots, self.slot_limit - self.count["offered"])
            if not slots:
                self.decode_s += perf_counter() - start
                return []
        self.count["offered"] += slots
        if not s["menu"]:
            self.count["no_menu"] += slots
            self.decode_s += perf_counter() - start
            return []
        page = Page(self.net, w, s)
        draws = page.draws(rng, slots, self.unique)
        empty = draws.count(None)
        tokens = [t for t in draws if t is not None]
        self.count.update(
            pages=1,
            attempted=len(draws),
            empty_parent=empty,
            signed=len(tokens),
            distribution_reads=page.net_calls,
        )
        skipped = slots - len(draws)
        self.count[
            "exhausted_page"
            if page.m.get("has_complete_domain", True)
            else "no_typed_token"
        ] += skipped
        self.decode_s += perf_counter() - start
        return tokens

    def append(self, row):
        s, tokens, replies = row
        self.pages.append(
            [
                s["run"],
                [
                    [t[0], t[1], STATUS[r[1]]]
                    for t, r in zip(tokens, replies, strict=True)
                ],
            ]
        )


def live(a):
    seeds = [int(x) for x in os.getenv("CB_SEEDS", "71 113").split()]
    draw = int(os.getenv("CB_DRAW", "193"))
    slot_limit = int(os.getenv("CB_SLOT_LIMIT", "0")) or None
    suffix = "" if draw == 193 else f"-draw{draw}"
    if slot_limit:
        suffix += f"-slots{slot_limit}"
    modes = os.getenv("CB_ARMS", "A B C").split()
    if not set(modes) <= {"A", "B", "C", "TB", "TC"}:
        raise ValueError(f"unknown study arms: {modes}")
    for case in os.getenv("CB_CASES", "fact loopfact sum-divisors").split():
        d, align = egg(a, case)
        nets = {}
        for seed in seeds:
            for trained in {m.startswith("T") for m in modes}:
                n = get(a, "visible", seed)
                if trained:
                    n.load_state_dict(
                        torch.load(
                            directory(a) / f"structured-{seed}.pt", weights_only=True
                        )
                    )
                nets[seed, trained] = n
        w = World(d, next(iter(nets.values())).actor, entry_table=None, sides="")
        for cap in map(int, os.getenv("CB_CAPS", "0 96 32").split()):
            for seed in seeds:
                path = (
                    directory(a)
                    / f"egg-{case}-{cap}-{seed}-{'_'.join(modes)}{suffix}.json"
                )
                rows = json.loads(path.read_text()) if path.exists() else []
                for rep in range(int(os.getenv("CB_REPS", "2"))):
                    for mode in reversed(modes) if rep % 2 else modes:
                        if any(r["mode"] == mode and r["rep"] == rep for r in rows):
                            continue
                        net = nets[seed, mode.startswith("T")]
                        net.condition_on_types = mode != "A"
                        net.static_cache.clear()
                        policy = TracePolicy(net, mode in ("C", "TC"), slot_limit)
                        z = native(
                            a,
                            w,
                            seed=draw,
                            slots=6,
                            submit_pages=2,
                            receipt_memory=True,
                            policy=policy,
                            reference=align,
                            paid_limit=cap or None,
                            receipt_log=policy,
                        )
                        assert z["stats"]["paid"] == policy.count["signed"]
                        rows.append(
                            dict(
                                case=case,
                                cap=cap,
                                slot_limit=slot_limit,
                                seed=seed,
                                draw=draw,
                                rep=rep,
                                mode=mode,
                                counts=dict(policy.count),
                                decode_s=policy.decode_s,
                                prepare_s=policy.prepare_s,
                                pages=policy.pages,
                                **z,
                            )
                        )
                        tmp = path.with_suffix(".tmp")
                        tmp.write_text(json.dumps(rows, separators=(",", ":")))
                        tmp.replace(path)
                        print(
                            case,
                            cap,
                            seed,
                            rep,
                            mode,
                            z["covered"],
                            policy.count["empty_parent"],
                            round(z["wall"], 2),
                            flush=True,
                        )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        live(args())
