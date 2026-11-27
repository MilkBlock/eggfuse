"""Native mixed-arity training, frozen decode ablations and request-level audits."""

import copy
import csv
import json
import os
import random
from collections import Counter
from itertools import product
from statistics import mean, median

import torch

from cell_kv_runtime import native
from cell_kv_study import digest
from cell_kv_world import World, make
from interface_role_train import dest
from interface_role_world import mixed
from partner_index_worlds import args
from selected_cell_model import SelectedCell
from value_read_world import CUBES, SCHEMAS, key

SEEDS = (71, 113)
STEPS = 420


def output(a):
    p = a.out / "selected-cell"
    p.mkdir(exist_ok=True)
    return p


def store(path, x):
    path.write_text(json.dumps(x, separators=(",", ":")))


def model(a, seed, mode, typed, trained=None):
    net = SelectedCell(a, mode, typed)
    path = (
        output(a) / f"{trained}-{seed}.pt"
        if trained
        else dest(a) / f"transfer-mixed-{seed}.pt"
    )
    net.load_state_dict(torch.load(path, weights_only=True))
    net.physical = ("held", 0)
    return net.eval()


def world(a, actor, kind, i, train):
    if kind == "single":
        s = SCHEMAS[i % 8]
        return World(
            a.out
            / "worlds"
            / key(s, 71001 + i // 8 if train else 81011, CUBES[(i + i // 8) % 8]),
            actor,
        )
    local = copy.copy(a)
    local.out = output(a)
    if kind == "fork":
        depth = 2 + i % 2 if train else 4
        seed = (184601 if train else 192801) + i
        return World(
            make(
                local,
                f"selected-fork-{seed}",
                depth,
                2 + i % 2,
                seed,
                fork=True,
                common=True,
            ),
            actor,
        )
    return mixed(
        local,
        actor,
        (154001 if train else 173101) + i // 2,
        i % 2,
        depth=1 + (i // 2 % 2) if train else 3,
        extra_rules=kind == "arity",
    )


def train(a):
    seed = int(os.environ["STUDY_SEED"])
    dist = os.environ["STUDY_CURRICULUM"]
    net = model(a, seed, "direct", True).train()
    data = {}
    domains = (
        ("single", "mixed", "arity", "fork")
        if dist == "diverse"
        else ("single", "mixed", "arity")
    )
    for kind in domains:
        data[kind] = []
        for i in range(12):
            w = world(a, net.actor, kind, i, True)
            traj = native(a, w, teacher="higher")
            data[kind].append((w, traj))
    store(
        output(a) / f"{dist}-training-signatures.json",
        sorted({k for pairs in data.values() for w, _ in pairs for k in digest(w)}),
    )
    rng = random.Random(seed)
    opt = torch.optim.AdamW(
        [p for p in net.parameters() if p.requires_grad], lr=0.001, weight_decay=0
    )
    curve = []
    counts = Counter()
    for step in range(STEPS):
        if dist == "mixed":
            kind = "mixed"
        else:
            # Retain the simple contexts in every phase.
            weights = ((6, 3, 1), (3, 4, 3), (2, 3, 5))[step * 3 // STEPS]
            if dist == "diverse":
                weights = ((12, 6, 1, 1), (6, 6, 4, 4), (4, 4, 6, 6))[step * 3 // STEPS]
            kind = rng.choices(list(data), weights)[0]
        w, traj = rng.choice(data[kind])
        losses = []
        for s, ts in (traj[0], rng.choice(traj[1:])):
            net.prepare(w)
            m = net.state(w, s)
            sample = rng.choices(ts, k=8)
            ps = {tok: net.token_loss(w, m, tok) for tok in set(sample)}
            losses.extend(ps[t] for t in sample)
            counts[kind] += len(sample)
        ce = torch.stack(losses).mean()
        opt.zero_grad(set_to_none=True)
        ce.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 3)
        opt.step()
        if step % 30 == 0 or step == STEPS - 1:
            curve.append([step + 1, float(ce.detach()), dict(counts)])
    torch.save(net.state_dict(), output(a) / f"{dist}-{seed}.pt")
    store(output(a) / f"{dist}-{seed}-curve.json", curve)


def reason(w, s, t, refs):
    ports = {p[0]: p for p in s["ports"]}
    for k, (expected, r) in enumerate(
        zip(w.roles[w.layouts[t][0][0]], refs, strict=True)
    ):
        p = ports[r]
        if p[3] == expected:
            continue
        if not any(x[3] == expected for x in s["ports"]):
            level = "no_declared_type_in_memory"
        elif not any(x[3] == expected and x[1] == p[1] for x in s["ports"]):
            level = "owner_without_declared_port"
        else:
            level = "wrong_port_on_compatible_owner"
        return level, k
    return "compatible", None


def wrong_mass(net, w, s):
    """Offline exact conditional mass; no full Cartesian product for a two-parent Cell."""
    m = net.state(w, s)
    total = 0.0
    for j, t in enumerate(m["menu"]):
        rid = w.layouts[t][0][0]
        roles = w.roles[rid]
        if not roles:
            continue
        assert len(roles) <= 2
        p = net.address(w, m, t, []).exp()
        bad = m["tables"] != roles[0]
        risk = p[bad].sum()
        if len(roles) > 1:
            for k in (~bad).nonzero().flatten().tolist():
                risk = (
                    risk
                    + p[k]
                    * net.address(w, m, t, [k]).exp()[m["tables"] != roles[1]].sum()
                )
        total += float(m["lp"][j].exp() * risk)
    return total


def run(a, study):
    arms = [
        ("free", "legacy", False, None),
        ("typed", "legacy", True, None),
        ("soft", "soft", False, None),
        ("direct", "direct", False, None),
        ("soft_t", "soft", True, None),
        ("direct_t", "direct", True, None),
    ]
    if study == "trained":
        arms = [
            ("direct_t", "direct", True, None),
            ("mixed", "direct", True, "mixed"),
            ("curriculum", "direct", True, "curriculum"),
        ]
    if study == "topology":
        arms = [(name, "direct", True, name) for name in ("curriculum", "diverse")]
    nets = {
        (name, seed): model(a, seed, mode, typed, trained)
        for name, mode, typed, trained in arms
        for seed in SEEDS
    }
    trials = []
    audit = []
    kinds = (
        ("single", "mixed", "arity", "fork")
        if study == "topology"
        else ("single", "mixed", "arity")
    )
    for kind in kinds:
        for i in range(4 if kind != "single" else 8):
            w = world(a, next(iter(nets.values())).actor, kind, i, False)
            if study in ("trained", "topology") and kind != "single":
                assert set(digest(w)).isdisjoint(
                    json.loads(
                        (
                            output(a)
                            / (
                                "diverse-training-signatures.json"
                                if study == "topology"
                                else "curriculum-training-signatures.json"
                            )
                        ).read_text()
                    )
                )
            for draw in (193, 827):
                for block in (0, 1):
                    order = list(nets)
                    if (block + i + (draw == 827)) % 2:
                        order.reverse()
                    for arm, seed in order:
                        net = nets[arm, seed]
                        net.static_cache.clear()
                        res = native(a, w, policy=net, seed=draw)
                        trials.append(
                            dict(
                                kind=kind,
                                i=i,
                                draw=draw,
                                block=block,
                                arm=arm,
                                seed=seed,
                                **res,
                            )
                        )
                # Repeat outside timing. Only the completed stream is analyzed.
                if study == "frozen":
                    for seed in SEEDS:
                        log = []
                        net = nets["free", seed]
                        result = native(a, w, policy=net, seed=draw, receipt_log=log)
                        match = next(
                            x
                            for x in reversed(trials)
                            if x["arm"] == "free" and x["seed"] == seed
                        )
                        assert (
                            result["graph"] == match["graph"]
                            and result["stats"] == match["stats"]
                        )
                        for s, decs, replies in log:
                            issued = []
                            for (t, rs), (uid, status, *_) in zip(
                                decs, replies, strict=True
                            ):
                                level, role = reason(w, s, t, rs)
                                issued.append(
                                    {
                                        "uid": uid,
                                        "t": t,
                                        "refs": rs,
                                        "status": status,
                                        "attribution": level,
                                        "parent": role,
                                    }
                                )
                            audit.append(
                                {
                                    "kind": kind,
                                    "i": i,
                                    "draw": draw,
                                    "seed": seed,
                                    "run": s["run"],
                                    "epoch": s["epoch"],
                                    "ports": [(p[0], p[1], p[3]) for p in s["ports"]],
                                    "menu": [
                                        (t, w.roles[w.layouts[t][0][0]])
                                        for t in s["menu"]
                                    ],
                                    "signed": issued,
                                    "risk": wrong_mass(net, w, s)
                                    if s["menu"]
                                    else None,
                                }
                            )
    store(output(a) / f"{study}-native.json", trials)
    if audit:
        store(output(a) / "audit.json", audit)
    ref = {"frozen": "free", "trained": "direct_t", "topology": "curriculum"}[study]
    baseline = {
        (r["kind"], r["i"], r["draw"], r["seed"], r["block"]): r
        for r in trials
        if r["arm"] == ref
    }
    rows = []
    for kind, arm, seed in product(kinds, [t[0] for t in arms], SEEDS):
        rr = [
            x for x in trials if (x["kind"], x["arm"], x["seed"]) == (kind, arm, seed)
        ]
        one = [x for x in rr if x["block"] == 0]
        ratios = []
        for x in rr:
            b = baseline[kind, x["i"], x["draw"], seed, x["block"]]
            if x["facts"] == b["facts"] and x["graph"] == b["graph"]:
                ratios.append(x["wall"] / b["wall"])
        rows.append(
            {
                "kind": kind,
                "arm": arm,
                "seed": seed,
                "n": len(one),
                "coverage": mean(x["coverage"] for x in one),
                "ept": mean(x["ept"] for x in one),
                "eps": mean(x["eps"] for x in rr),
                "ops": mean(x["ops"] for x in one),
                "paid": mean(x["stats"]["paid"] for x in one),
                "higher": mean(x["stats"]["higher_completed"] for x in one),
                "type_reject": mean(
                    x["receipts"]["rejected"].get("type", 0) for x in one
                ),
                "equal_graph": len(ratios) // 2,
                "wall_ratio": median(ratios) if ratios else "",
            }
        )
    with (output(a) / f"{study}.csv").open("w") as f:
        wr = csv.DictWriter(f, rows[0], lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    if a.task == "train":
        train(a)
    else:
        with torch.no_grad():
            run(a, os.environ.get("STUDY_PHASE", "frozen"))
