"""Offline path interventions and single-thread public-port read benchmarks."""

import csv
import random
from itertools import product
from statistics import median
from time import perf_counter_ns

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from operand_read_eval import load
from operand_read_train import dest
from partner_index_worlds import args
from value_read_train import SEEDS
from value_read_world import CUBES, key


def write(path, rows):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


@torch.no_grad()
def probe(a):
    nets = {s: load(a, "D", s) for s in SEEDS}
    rows = []
    for pool, g, o, bits in product(range(81011, 81015), range(2), range(2), CUBES):
        if bits[1] == bits[2]:
            continue
        worlds = [
            World(a.out / "worlds" / key((i, g, o), pool, bits), nets[71].actor)
            for i in range(2)
        ]
        events = [native(a, w, teacher="higher")[0] for w in worlds]
        assert events[0][0] == events[1][0]
        for seed, net in nets.items():
            desc = []
            for w in worlds:
                net.prepare(w)
                desc.append(net.descriptors)
            for mode in ("intact", "other_operand_nodes", "zero_operand_nodes"):
                margins = []
                correct = []
                for i, (w, (s, ts)) in enumerate(zip(worlds, events, strict=True)):
                    net.prepare(w)
                    if mode == "other_operand_nodes":
                        # Align by named left/right Higher and root, even if IDs differ.
                        for_this = net.descriptors.clone()
                        other = worlds[1 - i]
                        for local, remote in zip(
                            (w.root, w.primitives, w.primitives + 1),
                            (other.root, other.primitives, other.primitives + 1),
                            strict=True,
                        ):
                            for_this[local] = desc[1 - i][remote]
                        net.descriptors = for_this
                    elif mode == "zero_operand_nodes":
                        net.descriptors = torch.zeros_like(desc[i])
                    m = net.state(w, s)
                    (gold,) = [t for t, r in ts if t >= w.primitives]
                    margin = float(
                        m["lp"][m["menu"].index(w.primitives)]
                        - m["lp"][m["menu"].index(w.primitives + 1)]
                    )
                    margins.append(margin)
                    correct.append(margin * (1 - 2 * (gold - w.primitives)) > 0)
                rows.append(
                    {
                        "seed": seed,
                        "pool": pool,
                        "g": g,
                        "o": o,
                        "bits": "".join(map(str, bits)),
                        "mode": mode,
                        "both": all(correct),
                        "neither": not any(correct),
                        "m0": margins[0],
                        "m1": margins[1],
                    }
                )
            net.static_cache.clear()
    write(dest(a) / "interventions.csv", rows)


@torch.no_grad()
def early(a):
    # Compute the same wiring flips before any update and after the single-Recipe curriculum.
    checkpoints = {
        (seed, step): load(a, "D", seed, step)
        for seed, step in ((71, 0), (71, 420), (113, 420))
    }
    counts = {key: [0, 0] for key in checkpoints}
    for pool, g, o, bits in product(range(81011, 81015), range(2), range(2), CUBES):
        if bits[1] == bits[2]:
            continue
        pair = []
        for i in range(2):
            w = World(
                a.out / "worlds" / key((i, g, o), pool, bits), checkpoints[71, 0].actor
            )
            s, ts = native(a, w, teacher="higher")[0]
            (gold,) = [t for t, r in ts if t >= w.primitives]
            pair.append((w, s, gold))
        assert pair[0][1] == pair[1][1]
        for ident, net in checkpoints.items():
            wins = []
            for w, s, gold in pair:
                net.prepare(w)
                m = net.state(w, s)
                other = w.primitives + 1 - (gold - w.primitives)
                wins.append(
                    m["lp"][m["menu"].index(gold)] > m["lp"][m["menu"].index(other)]
                )
            counts[ident][0] += int(all(wins))
            counts[ident][1] += 1
            net.static_cache.clear()
    write(
        dest(a) / "early.csv",
        [
            {"seed": s, "step": u, "both": n, "pairs": t}
            for (s, u), (n, t) in counts.items()
        ],
    )


@torch.no_grad()
def costs(a):
    nets = {arm: load(a, arm, 71) for arm in "ABCD"}
    w = World(a.out / "worlds" / key((0, 0, 0), 81011, CUBES[0]), nets["A"].actor)
    s, _ = native(a, w, teacher="higher")[0]
    for net in nets.values():
        net.prepare(w)
        net.state(w, s)
    rng = random.Random(3101)
    q = torch.randn(len(s["menu"]), 32, generator=torch.Generator().manual_seed(71))
    rows = []
    for f in (4, 8, 16, 32, 64, 128):
        ports = [
            (*p[:4], tuple(rng.getrandbits(64) for _ in range(f)), *p[5:])
            for p in s["ports"]
        ]
        timings = {arm: [] for arm in nets}
        for block in range(12):
            order = list(nets) if block % 2 == 0 else list(reversed(nets))
            for arm in order:
                start = perf_counter_ns()
                for _ in range(12):
                    nets[arm].read_interface(q, ports)
                if block >= 2:
                    timings[arm].append((perf_counter_ns() - start) / 12000)
        for arm, vals in timings.items():
            rows.append(
                {
                    "arm": arm,
                    "fields": f,
                    "templates": len(q),
                    "owners": len(ports),
                    "relation_terms": f * (f - 1) // 2 if arm in "AB" else 2 * f,
                    "median_us": median(vals),
                    "min_us": min(vals),
                    "max_us": max(vals),
                }
            )
    write(dest(a) / "cost.csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    probe(a)
    early(a)
    costs(a)
