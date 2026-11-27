"""Within-state interventions. Direct reads and exchanged contracts stay offline."""

import copy
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from cell_kv_runtime import native
from cell_kv_world import World
from interface_role_eval import distribution, load
from interface_role_model import RoleRead
from interface_role_train import dest
from interface_role_world import mixed
from operand_read_probe import write
from partner_index_worlds import args
from value_read_train import SEEDS
from value_read_world import CUBES, key


@torch.no_grad()
def controls(a):
    nets = {s: load(a, "C", s) for s in SEEDS}
    probe = []
    for pool, g, o, bits in product(range(81011, 81015), range(2), range(2), CUBES):
        if bits[1] == bits[2]:
            continue
        worlds = [
            World(a.out / "worlds" / key((i, g, o), pool, bits), nets[71].actor)
            for i in (0, 1)
        ]
        events = [native(a, w, teacher="higher")[0] for w in worlds]
        assert events[0][0] == events[1][0]
        for seed, net in nets.items():
            contracts = []
            for w in worlds:
                net.prepare(w)
                contracts.append(net.columns)
            for mode in ("intact", "remove", "exchange", "hard"):
                correct = []
                for i, (w, (s, targets)) in enumerate(zip(worlds, events, strict=True)):
                    net.physical = ("held", 0)
                    net.hard = mode == "hard"
                    net.prepare(w)
                    if mode == "remove":
                        net.columns = torch.full_like(net.columns, -1)
                    if mode == "exchange":
                        cols = net.columns.clone()
                        cols[w.primitives :] = contracts[1 - i][
                            worlds[1 - i].primitives :
                        ]
                        net.columns = cols
                    m, lp, _ = distribution(net, w, s)
                    (tok,) = [t for t, r in targets if t >= w.primitives]
                    ix = [
                        m["menu"].index(t) for t in range(w.primitives, len(w.layouts))
                    ]
                    correct.append(int(lp[ix, 0].argmax()) == tok - w.primitives)
                probe.append(
                    {
                        "pool": pool,
                        "g": g,
                        "o": o,
                        "bits": str(bits),
                        "seed": seed,
                        "mode": mode,
                        "both": all(correct),
                        "neither": not any(correct),
                    }
                )
            net.hard = False
            net.static_cache.clear()
    write(dest(a) / "controls.csv", probe)


@torch.no_grad()
def rollout_pairs(a):
    nets = {(arm, seed): load(a, arm, seed) for arm, seed in product("ABC", SEEDS)}
    rows = []
    for pool, wire in product(range(124081, 124084), (0, 1)):
        with TemporaryDirectory() as tmp:
            local = copy.copy(a)
            local.out = Path(tmp)
            w = mixed(local, nets["A", 71].actor, pool, wire)
            for (arm, seed), net in nets.items():
                for draw in (193, 827):
                    net.physical = ("train", 0)
                    first = native(a, w, policy=net, seed=draw)
                    for idx in (0, 1):
                        net.physical = ("held", idx)
                        other = native(a, w, policy=net, seed=draw)
                        rows.append(
                            {
                                "arm": arm,
                                "seed": seed,
                                "pool": pool,
                                "wire": wire,
                                "draw": draw,
                                "idx": idx,
                                "graph": first["graph"] == other["graph"],
                                "facts": first["facts"] == other["facts"],
                                "requests": first["stats"] == other["stats"],
                                "ops": first["ops"] == other["ops"],
                            }
                        )
                net.static_cache.clear()
    write(dest(a) / "rollout-pairs.csv", rows)


@torch.no_grad()
def mixed_probabilities(a):
    nets = {(arm, seed): load(a, arm, seed) for arm, seed in product("ABC", SEEDS)}
    rows = []
    for pool, wire in product(range(124081, 124084), (0, 1)):
        with TemporaryDirectory() as tmp:
            local = copy.copy(a)
            local.out = Path(tmp)
            w = mixed(local, nets["C", 71].actor, pool, wire)
            s, ts = native(a, w, teacher="higher")[0]
            for (arm, seed), net in nets.items():
                net.prepare(w)
                net.physical = ("held", 0)
                m, _lp, p = distribution(net, w, s)
                hi = [j for j, t in enumerate(m["menu"]) if t >= w.primitives]
                correct = torch.zeros_like(p, dtype=torch.bool)
                for t, (ref,) in ts:
                    correct[m["menu"].index(t), m["pos"][ref]] = True
                hp = float(p[hi].sum())
                joint = float((p * correct)[hi].sum())
                distinct = float((1 - (1 - p) ** 6)[correct].sum())
                rows.append(
                    {
                        "pool": pool,
                        "wire": wire,
                        "seed": seed,
                        "arm": arm,
                        "higher_mass": hp,
                        "valid_higher": joint,
                        "valid_ref_given_higher": joint / hp,
                        "distinct_valid_at_six": distinct,
                        "valid_tokens": int(correct.sum()),
                        "top_token": float(p.max()),
                        "valid_total": float(p[correct].sum()),
                    }
                )
                net.static_cache.clear()
    write(dest(a) / "mixed-probability.csv", rows)


@torch.no_grad()
def checkpoints(a):
    nets = {}
    for step, seed in ((0, 71), (420, 71), (420, 113), (1680, 71), (1680, 113)):
        net = RoleRead(a, "C").eval()
        before = [
            p.detach().clone()
            for p in (net.actor.query.weight, net.actor.input_role.weight)
        ]
        if step:
            net.load_state_dict(
                torch.load(dest(a) / f"C-{seed}-{step}.pt", weights_only=True)
            )
        change = [
            float((p - u).norm())
            for p, u in zip(
                (net.actor.query.weight, net.actor.input_role.weight),
                before,
                strict=True,
            )
        ]
        nets[step, seed] = (net, change, [])
    for pool, g, o, bits in product(range(81011, 81015), range(2), range(2), CUBES):
        if bits[1] == bits[2]:
            continue
        pair = []
        for wire in range(2):
            w = World(
                a.out / "worlds" / key((wire, g, o), pool, bits), nets[0, 71][0].actor
            )
            s, ts = native(a, w, teacher="higher")[0]
            (t,) = [tid for tid, r in ts if tid >= w.primitives]
            pair.append((w, s, t))
        for net, _, wins in nets.values():
            correct = []
            for w, s, t in pair:
                net.physical = ("held", 0)
                net.prepare(w)
                m, lp, _ = distribution(net, w, s)
                ix = [m["menu"].index(i) for i in range(w.primitives, len(w.layouts))]
                correct.append(int(lp[ix, 0].argmax()) == t - w.primitives)
            wins.append(all(correct))
            net.static_cache.clear()
    write(
        dest(a) / "checkpoints.csv",
        [
            {
                "step": i,
                "seed": k,
                "pairs": len(r),
                "flips": sum(r),
                "delta_Wq": c[0],
                "delta_Wrole": c[1],
            }
            for (i, k), (_, c, r) in nets.items()
        ],
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    controls(a)
    rollout_pairs(a)
    mixed_probabilities(a)
    checkpoints(a)
