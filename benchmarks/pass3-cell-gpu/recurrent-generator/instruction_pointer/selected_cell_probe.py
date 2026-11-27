"""Measure withheld interface reads, full-token gradients and retention."""

import copy
import csv
from collections import defaultdict
from itertools import product
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory

import torch

from cell_kv_runtime import native
from interface_role_train import dest
from operand_read_eval import fixture
from selected_cell_study import SEEDS, args, model, output, store
from value_read_world import CUBES


def probe(a):
    detailed = []
    gradients = []
    training_p = []
    for seed in SEEDS:
        for mode in ("soft", "direct"):
            net = model(a, seed, mode, True)
            # Isolate reading on the previous successful single-entry policy as well.
            net.load_state_dict(
                torch.load(dest(a) / f"C-{seed}-1680.pt", weights_only=True)
            )
            for wire, g, o in product(range(2), repeat=3):
                for pool in (124081, 124082):
                    for bits in ((0, 0, 1), (0, 1, 0)):
                        with TemporaryDirectory() as tmp:
                            b = copy.copy(a)
                            b.out = Path(tmp)
                            w = fixture(b, net.actor, "shift", (wire, g, o), pool, bits)
                            s, ts = native(a, w, teacher="higher")[0]
                            net.prepare(w)
                            net.physical = ("held", 0)
                            net.audit = True
                            m = net.state(w, s)
                            gold = next((t, r) for t, r in ts if t >= w.primitives)
                            loss = net.token_loss(w, m, gold)
                            if mode == "direct":
                                vs = (
                                    net.projected_values,
                                    net.projected_relation,
                                    net.actor.input_role.weight,
                                    net.actor.query.weight,
                                )
                                gradients.append(
                                    [
                                        seed,
                                        *[
                                            float(x.norm())
                                            for x in torch.autograd.grad(loss, vs)
                                        ],
                                    ]
                                )
                            with torch.no_grad():
                                scores = [
                                    float(-net.token_loss(w, m, (t, gold[1])))
                                    for t in range(w.primitives, len(w.layouts))
                                ]
                                raw = float(loss.detach().neg().exp())
                                net.audit = False
                                result = native(a, w, policy=net, seed=193)
                            detailed.append(
                                {
                                    "seed": seed,
                                    "mode": mode,
                                    "pool": pool,
                                    "wire": wire,
                                    "g": g,
                                    "o": o,
                                    "bits": bits,
                                    "gold": gold[0] - w.primitives,
                                    "correct": scores.index(max(scores))
                                    == gold[0] - w.primitives,
                                    "prob": raw,
                                    "coverage": result["coverage"],
                                    "ept": result["ept"],
                                    "ops": result["ops"],
                                }
                            )
                            net.static_cache.clear()
    # Quantify retention of the original conflict test; include both selections in full-token probabilities.
    for seed, trained in product(SEEDS, (None, "mixed", "curriculum", "diverse")):
        net = model(a, seed, "direct", True, trained)
        for pool, g, o in product(range(81011, 81015), range(2), range(2)):
            for bits in CUBES:
                pair = []
                for wire in (0, 1):
                    w = fixture(a, net.actor, "known", (wire, g, o), pool, bits)
                    s, ts = native(a, w, teacher="higher")[0]
                    net.prepare(w)
                    with torch.no_grad():
                        m = net.state(w, s)
                        t, r = next((t, r) for t, r in ts if t >= w.primitives)
                        scores = [
                            float(-net.token_loss(w, m, (v, r)))
                            for v in range(w.primitives, len(w.layouts))
                        ]
                    pair.append((t - w.primitives, scores.index(max(scores))))
                    net.static_cache.clear()
                if pair[0][0] != pair[1][0]:
                    training_p.append(
                        {
                            "seed": seed,
                            "trained": trained or "frozen",
                            "pool": pool,
                            "g": g,
                            "o": o,
                            "bits": bits,
                            "both": all(x == y for x, y in pair),
                        }
                    )
    store(
        output(a) / "projection-probe.json",
        {"shift": detailed, "grad": gradients, "retention": training_p},
    )
    summary = []
    for mode, seed in product(("soft", "direct"), SEEDS):
        rows = [r for r in detailed if (r["mode"], r["seed"]) == (mode, seed)]
        pairs = defaultdict(list)
        for r in rows:
            pairs[r["pool"], r["g"], r["o"], tuple(r["bits"])].append(r)
        assert all(len(p) == 2 and p[0]["gold"] != p[1]["gold"] for p in pairs.values())
        summary.append(
            {
                "mode": mode,
                "seed": seed,
                "pairs": len(pairs),
                "both": sum(all(r["correct"] for r in p) for p in pairs.values()),
                "p_full": mean(r["prob"] for r in rows),
                "coverage": mean(r["coverage"] for r in rows),
            }
        )
    with (output(a) / "projection.csv").open("w") as f:
        wr = csv.DictWriter(f, summary[0], lineterminator="\n")
        wr.writeheader()
        wr.writerows(summary)


if __name__ == "__main__":
    torch.set_num_threads(1)
    probe(args())
