"""Frozen wiring interventions at a fixed native singleton entry. Offline diagnostics."""

import csv
import json
from itertools import product
from pathlib import Path
from statistics import mean

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from partner_index_worlds import args
from value_read_model import ValueRead, lane_products
from value_read_train import SEEDS, STEPS
from value_read_world import CUBES, filler_values, key


def capture(net, world, state):
    net.prepare(world)
    memory = net.state(world, state)
    assert len(memory["owners"]) == len(state["ports"]) == 1
    tids = list(range(world.primitives, len(world.layouts)))
    idx = [memory["menu"].index(t) for t in tids]
    assert len(tids) == 2
    nodes, codes, _ = net.cache
    ids = [world.layouts[t][1][0] for t in tids]
    roots = nodes[[world.cat.roots["generated", r] for r in ids]]
    inputs = nodes[[world.cat.inputs["generated", r][0] for r in ids]]
    c = codes[tids]
    ctx = memory["ctx"]
    q = net.actor.query(ctx + c)
    lanes, roles = lane_products([state["ports"][0][4]])
    # Each row is one Higher, each column a different intra-port position pair.
    relation = q.softmax(-1) @ lanes[0].T
    payload = net.read_interface(q, state["ports"])[:, 0]
    torch.testing.assert_close(relation @ roles, payload)
    base = memory["vals"][0] + net.actor.latent(memory["ext"])[0]
    logits = net.template_readout(ctx, base + payload, c)
    margin = logits[0] - logits[1]
    torch.testing.assert_close(
        margin, memory["lp"][idx[0]] - memory["lp"][idx[1]], atol=1e-5, rtol=1e-5
    )
    return {
        "root": roots,
        "input_atom": inputs,
        "code": c,
        "query": q,
        "lane_weights": q.softmax(-1),
        "pair_relation": relation,
        "payload": payload,
        "ctx": ctx,
        "base": base,
        "margin": margin,
    }


def compare(net, traces, gold):
    left, right = traces
    assert torch.equal(left["ctx"], right["ctx"]) and torch.equal(
        left["base"], right["base"]
    )
    # Four crossed scores. i supplies all direct Recipe readout paths, j the
    # Recipe-conditioned interface payload. Both come from the same real state.
    scores = []
    for i, j in product(range(2), repeat=2):
        logit = net.template_readout(
            left["ctx"], left["base"] + traces[j]["payload"], traces[i]["code"]
        )
        scores.append(float(logit[0] - logit[1]))
    m00, m01, m10, m11 = scores
    torch.testing.assert_close(
        torch.tensor([m00, m11]), torch.stack([a["margin"] for a in traces])
    )
    correct = [m * (1 - 2 * g) > 0 for m, g in zip((m00, m11), gold, strict=True)]
    # Average each path's marginal change over both intervention orders.
    field = ((m01 - m00) + (m11 - m10)) / 2
    direct = ((m10 - m00) + (m11 - m01)) / 2
    row = {
        "gold_xy": gold[0],
        "gold_xz": gold[1],
        "conflict": gold[0] != gold[1],
        "both_correct": all(correct),
        "ranking_changed": m00 * m11 < 0,
        "m00": m00,
        "m01": m01,
        "m10": m10,
        "m11": m11,
        "field_margin": field,
        "direct_margin": direct,
    }
    for name in (
        "root",
        "input_atom",
        "code",
        "query",
        "lane_weights",
        "pair_relation",
        "payload",
    ):
        diff = left[name] - right[name]
        row[name + "_mean_l2"] = float(diff.norm(dim=1).mean())
        row[name + "_max_abs"] = float(diff.abs().max())
    return row


@torch.no_grad()
def run(a):
    nets = {}
    for seed in SEEDS:
        model = ValueRead(a, "C").eval()
        model.load_state_dict(
            torch.load(a.out / "rich" / f"C-{seed}-{STEPS}.pt", weights_only=True)
        )
        nets[seed] = model
    pools = range(81011, 81015)
    train_values = set().union(*(set(filler_values(p)) for p in range(72001, 72033)))
    assert all(train_values.isdisjoint(filler_values(p)) for p in pools)
    rows = []
    for g, o, pool, bits in product(range(2), range(2), pools, CUBES):
        worlds = [
            World(a.out / "worlds" / key((w, g, o), pool, bits), nets[SEEDS[0]].actor)
            for w in range(2)
        ]
        assert worlds[0].prog["recipe"]["sha256"] != worlds[1].prog["recipe"]["sha256"]
        events = [native(a, w, teacher="higher")[0] for w in worlds]
        assert events[0][0] == events[1][0]
        targets = []
        for w, (_, ts) in zip(worlds, events, strict=True):
            (t,) = [t for t, _ in ts if t >= w.primitives]
            targets.append(t - w.primitives)
        for seed, net in nets.items():
            traces = [
                capture(net, w, s) for w, (s, _) in zip(worlds, events, strict=True)
            ]
            rows.append(
                dict(
                    seed=seed,
                    guard=g,
                    arithmetic=o,
                    pool=pool,
                    bits="".join(map(str, bits)),
                    **compare(net, traces, targets),
                )
            )
            net.static_cache.clear()
    dest = Path("run-recall/conditional-value")
    with (dest / "wiring-path.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = []
    for seed, conflict in product(SEEDS, (False, True)):
        group = [r for r in rows if r["seed"] == seed and r["conflict"] == conflict]
        summary.append(
            {
                "seed": seed,
                "conflict": conflict,
                "pairs": len(group),
                "correct": sum(r["both_correct"] for r in group),
                "changed": sum(r["ranking_changed"] for r in group),
                "avg_absolute_field": mean(abs(r["field_margin"]) for r in group),
                "avg_absolute_direct": mean(abs(r["direct_margin"]) for r in group),
                "mean_l2": {
                    k: mean(r[k] for r in group)
                    for k in rows[0]
                    if k.endswith("_mean_l2")
                },
            }
        )
    (dest / "wiring-path-summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
