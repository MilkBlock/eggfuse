"""Free generation on real EggCC Recipes with a common Primitive deployment catalogue."""

import json
import os
from itertools import product

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from competition_egg import egg
from constructible_study import TracePolicy
from foundation_fit import model
from foundation_world import folder
from partner_index_worlds import args


def run(a):
    root = folder(a)
    for case, cap in product(
        os.getenv("FC_EGG", "fact loopfact sum-divisors").split(), (96, 0)
    ):
        rows = []
        arms = [
            "initial",
            "multi-24-32",
            "multi-24-512",
            "multi-48-32",
            "long-multi-24-32",
        ]
        if cap:
            arms += [
                "multi-4-32",
                "primitive-12-32",
                "short-12-32",
                "medium-12-32",
                "multi-12-32",
                "wake-fit",
            ]
        p = root / f"egg-{case}-{cap}.json"
        if p.exists():
            rows = json.loads(p.read_text())
        ir, align = egg(a, case)
        for seed in (71, 113):
            for rep in (0, 1):
                for label in reversed(arms) if rep else arms:
                    if any(
                        (r["seed"], r["rep"], r["label"]) == (seed, rep, label)
                        for r in rows
                    ):
                        continue
                    width = (
                        32
                        if label in ("initial", "wake-fit")
                        else int(label.split("-")[-1])
                    )
                    net = model(a, seed, width)
                    if label != "initial":
                        ckpt = root / (
                            f"wake-fit-{seed}.pt"
                            if label == "wake-fit"
                            else f"model-{label}-{seed}.pt"
                        )
                        net.load_state_dict(torch.load(ckpt, weights_only=True))
                    w = World(ir, net.actor, entry_table=None, sides="")
                    pol = TracePolicy(net, True)
                    z = native(
                        a,
                        w,
                        seed=193,
                        policy=pol,
                        slots=6,
                        submit_pages=2,
                        receipt_memory=True,
                        paid_limit=cap or None,
                        reference=align,
                        receipt_log=pol,
                    )
                    rows.append(
                        dict(
                            label=label,
                            seed=seed,
                            rep=rep,
                            case=case,
                            cap=cap,
                            decode=pol.decode_s,
                            offered=pol.count["offered"],
                            **z,
                        )
                    )
                    tmp = p.with_suffix(".tmp")
                    tmp.write_text(json.dumps(rows, separators=(",", ":")))
                    tmp.replace(p)
                    print(case, cap, seed, rep, label, z["covered"], flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
