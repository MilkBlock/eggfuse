"""Native branch tasks with independently controlled interface and catalogue size."""

import os
import pickle
import random

import torch

from cell_kv_runtime import native
from cell_kv_world import World, compile_world
from competition_corpus import rowskey
from feedback_train import get
from partner_index_worlds import args

CATS = ("primitive", "short", "medium", "multi", "half", "medium-half")


def folder(a):
    d = a.out / "foundation-curves"
    d.mkdir(exist_ok=True)
    return d


def source(depth, jobs, arity, seed):
    rng = random.Random(seed)
    side = list("LRUV")
    lines = [
        "(relation Seed (i64 i64))",
        "(relation Permit (i64))",
        "(relation Mid (i64 i64))",
        "(ruleset root)",
        "(ruleset finish)",
    ]
    extra = " (Permit x)" if arity == 2 else ""
    lines.append(f"(rule ((Seed x y){extra}) ((Mid x y)) :ruleset root)")
    for j in range(depth):
        lines.append(f"(ruleset step{j})")
        rng.shuffle(side)
        for b in side:
            old = "Mid" if not j else f"{b}{j - 1}"
            name = f"{b}{j}"
            guard = (" (= x y)" if b in "LU" else " (!= x y)") if not j else ""
            delta = (1 + "LRUV".index(b)) * (j + 1)
            lines.extend(
                [
                    f"(relation {name} (i64 i64))",
                    f"(rule (({old} x y){guard}) (({name} x (+ y {delta}))) :ruleset step{j})",
                ]
            )
    for b in side:
        lines.extend(
            [
                f"(relation Done{b} (i64 i64))",
                f"(rule (({b}{depth - 1} x y) (Permit x)) ((Done{b} x y)) :ruleset finish)",
            ]
        )
    vals = rng.sample(range(10000, 9000000), 2 * jobs)
    inputs = []
    for j in range(jobs):
        x = vals[2 * j]
        y = x if (j + seed) % 2 else vals[2 * j + 1]
        inputs += [f"(Seed {x} {y})", f"(Permit {x})"]
    rng.shuffle(inputs)
    lines += inputs + [
        "(run-schedule (run root) "
        + " ".join(f"(run step{j})" for j in range(depth))
        + " (run finish) (run finish))"
    ]
    return "\n".join(lines) + "\n"


def world(a, actor, i, train, cat):
    # Consecutive groups of four cross difficulty with arity; nested subsets remain balanced.
    arity = 1 + i % 2
    jobs = (2 if i % 4 < 2 else 5) if train else (5 if i % 4 < 2 else 7)
    depth = (3 if i % 4 < 2 else 5) if train else (4 if i % 4 < 2 else 6)
    seed = (252200 if train else 617700) + i // 2
    d = compile_world(
        a,
        f"foundation-{seed}-j{jobs}-a{arity}-d{depth}",
        source(depth, jobs, arity, seed),
    )
    w = World(d, actor, sides="")
    for size in (2, depth + 1):
        if cat not in (
            ("short", "half", "multi")
            if size == 2
            else ("medium", "medium-half", "multi")
        ):
            continue
        for b in (
            ("LR" if (seed % 2 == 0) else "UV")
            if cat in ("half", "medium-half")
            else "LRUV"
        ):
            body = list(w.layouts[w.root])
            prev = "Mid"
            for j in range(size - 1):
                dest = f"{b}{j}"
                rid = w.outnames[dest]
                body.append((rid, len(body), [(j, w.outputs[body[-1][0]][prev])]))
                prev = dest
            w.export_pc[len(w.layouts)] = w.outputs[body[-1][0]][prev]
            w.layouts.append(body)
    return w


def dataset(a, w, path):
    if path.exists():
        return pickle.loads(path.read_bytes())
    samples = []
    for s, proofs in native(a, w, teacher="primitive", receipt_memory=True):

        def replay(actions, state=s):
            return native(
                a, w, teacher="primitive", branch=(state, actions), receipt_memory=True
            )

        base = rowskey(replay([]))
        tokens = set()
        for tid, refs in proofs:
            if tid < w.primitives:
                tokens.add((tid, refs))
                if tid == w.root:
                    tokens.update(
                        (h, refs) for h in range(w.primitives, len(w.layouts))
                    )
        targets = []
        for t in sorted(tokens):
            z = replay([t])
            if base < rowskey(z) and (
                t[0] < w.primitives or z["stats"]["branch_higher_completed"]
            ):
                targets.append(t)
        if targets:
            samples.append((s, targets))
    if not samples:
        raise ValueError("empty native corpus")
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(samples))
    tmp.replace(path)
    return samples


def data(a, actor, cat, train, n):
    return [
        (w, dataset(a, w, folder(a) / f"states-{cat}-{int(train)}-{i}.pkl"))
        for i in range(n)
        for w in [world(a, actor, i, train, cat)]
    ]


if __name__ == "__main__":
    a = args()
    torch.set_num_threads(1)
    actor = get(a, "visible", 71).actor
    for cat in os.getenv("FC_CATS", "primitive short medium multi half").split():
        for train, n in ((True, 12), (False, 4)):
            with torch.no_grad():
                ds = data(a, actor, cat, train, n)
            print(cat, train, sum(len(rows) for _, rows in ds), flush=True)
