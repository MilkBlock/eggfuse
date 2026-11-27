"""Fixed-state discovery curves and free native rollouts without online target access."""

import copy
import pickle
from collections import Counter
from itertools import product

import numpy as np
import torch

from cell_kv_runtime import native
from cell_kv_world import World, compile_world
from competition_corpus import audit, candidates, out, rowskey, world
from competition_draw import Page, Policy
from competition_egg import network
from partner_index_worlds import args
from selected_cell_study import store

ARMS = ("prior", "previous", "A", "B", "C")
BUDGETS = (4, 6, 16, 64, 256)


def zero_world(a, actor, n):
    b = copy.copy(a)
    b.out = out(a)
    # Real zero-parent rules in a standalone schedule; one unrelated initial Cell.
    lines = ["(relation Seed (i64))", "(Seed 4)", "(ruleset entry)"]
    for j, name in enumerate(("StartMark", "ZeroOther", "ZeroThird")[:n]):
        lines.extend(
            [
                f"(relation {name} (i64))",
                f"(rule () (({name} {17 + j})) :ruleset entry)",
            ]
        )
    lines.append("(run-schedule (run entry))")
    d = compile_world(b, f"zero-independent-{n}", "\n".join(lines) + "\n")
    return World(d, actor, sides="", entry_table=None)


def target_mass(net, w, s, v):
    m = net.state(w, s)
    totals = Counter()
    for t, r in candidates(w, s):
        lp = net.token_loss(w, m, (t, r))
        p = float((-lp).exp())
        totals[f"arity{len(r)}"] += p
        if (t, r) in v:
            totals[f"verified{len(r)}"] += p
            if any(g[0] == "StartMark" for g in v[t, r]):
                totals["start"] += p
    assert sum(totals[f"arity{i}"] for i in range(3)) < 1.00001
    return dict(totals)


def stats(tokens, ver):
    complete = [t for t in tokens if t is not None]
    hit = {t for t in complete if t in ver}
    effects = {ver[t] for t in hit}
    contributed = {f for g in effects for f in g}
    counts = Counter(f"draw{len(rs)}" for _, rs in complete)
    for j in (0, 1, 2):
        group = {ver[t] for t in hit if len(t[1]) == j}
        counts[f"effects{j}"] = len(group)
        counts[f"found{j}"] = bool(group)
    by_type = Counter(f"facts_{table}" for table, vals in contributed)
    return dict(
        attempts=len(tokens),
        signed=len(complete),
        physical_dup=len(complete) - len(set(complete)),
        known_effects=len(effects),
        union_facts=len(contributed),
        **counts,
        **by_type,
    )


def frozen(a):
    nets = {
        (arm, seed): network(a, arm, seed) for arm, seed in product(ARMS, (71, 113))
    }
    raw = []
    masses = []
    batches = []
    actor = next(iter(nets.values())).actor
    for k in ("zero1", "zero3", "arity", "aliases"):
        for i in range(1 if k.startswith("zero") else 4):
            if k.startswith("zero"):
                w = zero_world(a, actor, int(k[-1]))
                s, _ = native(a, w, teacher="higher")[0]
                ver, _ = audit(a, w, s)
            else:
                w = world(a, actor, k, i, False)
                s, _ts, ver, _ = pickle.loads(
                    (out(a) / f"test-{k}-{i}.pkl").read_bytes()
                )[0]
            empty = native(a, w, teacher="higher", branch=(s, []))
            baseline = rowskey(empty)
            for (arm, seed), net in nets.items():
                meta = {"kind": k, "case": i, "arm": arm, "seed": seed}
                net.prepare(w)
                masses.append(dict(**meta, **target_mass(net, w, s, ver)))
                page = Page(net, w, s)
                for unique in (False, True):
                    mode = "unique" if unique else "iid"
                    # Common, independent page seeds for all compared weights.
                    for draw in range(32):
                        draws = page.draws(
                            np.random.default_rng(60217 + draw), 256, unique
                        )
                        for budget in BUDGETS:
                            tokens = draws[:budget]
                            raw.append(
                                dict(
                                    **meta,
                                    mode=mode,
                                    draw=draw,
                                    budget=budget,
                                    **stats(tokens, ver),
                                )
                            )
                            # Paired batch replay additionally checks partial overlap and
                            # contention of a Primitive and a Higher claiming the same root.
                            if (
                                i == 0
                                and draw < 2
                                and (arm in ("A", "B", "C") or budget == 6)
                            ) or (k == "arity" and budget == 6 and draw < 4):
                                res = native(
                                    a,
                                    w,
                                    teacher="higher",
                                    branch=(s, [t for t in tokens if t is not None]),
                                )
                                delta = rowskey(res) - baseline
                                batches.append(
                                    dict(
                                        **meta,
                                        mode=mode,
                                        draw=draw,
                                        budget=budget,
                                        actual=len(delta),
                                        paid=res["stats"]["paid"],
                                        ops=res["ops"] - empty["ops"],
                                        new_by_table=dict(Counter(t for t, v in delta)),
                                        signed=res["stats"].get("neural_tokens", 0),
                                    )
                                )
                net.static_cache.clear()
    store(out(a) / "mass.json", masses)
    store(out(a) / "curves.json", raw)
    store(out(a) / "batches.json", batches)


def live(a):
    nets = {
        (arm, seed): network(a, arm, seed) for arm, seed in product(ARMS, (71, 113))
    }
    actor = next(iter(nets.values())).actor
    rows = []
    for k in ("single", "mixed", "arity", "aliases", "fork", "zero1", "zero3"):
        for i in range(1 if k.startswith("zero") else 4):
            w = (
                zero_world(a, actor, int(k[-1]))
                if k.startswith("zero")
                else world(a, actor, k, i, False)
            )
            for draw, block in product((193, 827), (0, 1)):
                order = list(product(nets, (False, True)))
                if (block + i + (draw == 827)) % 2:
                    order.reverse()
                for (arm, seed), unique in order:
                    net = nets[arm, seed]
                    net.static_cache.clear()
                    policy = Policy(net, unique)
                    result = native(a, w, policy=policy, seed=draw)
                    rows.append(
                        dict(
                            kind=k,
                            case=i,
                            draw=draw,
                            block=block,
                            seed=seed,
                            arm=arm,
                            mode="unique" if unique else "iid",
                            attempts=policy.slots,
                            empty=policy.empty,
                            kernels=policy.calls,
                            **result,
                        )
                    )
        store(out(a) / "live.json", rows)


if __name__ == "__main__":
    import os

    torch.set_num_threads(1)
    with torch.no_grad():
        (frozen if os.environ["COMP_PHASE"] == "frozen" else live)(args())
