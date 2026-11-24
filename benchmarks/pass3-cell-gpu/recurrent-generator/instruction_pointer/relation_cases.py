"""Enumerate typed owner projections using only sealed visibility and rule watermarks."""

from collections import Counter, defaultdict
import json
import random

from composition_relation import Interfaces, Store, encode
from higher_cell import read


def select_runs(tape, nruns, seed, count):
    rng = random.Random(seed)
    busy = {q["run"] for q in tape["requests"]}
    empty = set(range(1, nruns + 1)) - busy
    return sorted(
        rng.sample(sorted(busy), min(count, len(busy)))
        + rng.sample(sorted(empty), min(count // 4, len(empty)))
    )


def episodes(folder, count, seed, visit, rename_seed=None):
    tape = read(folder / "tape.json")
    runs = select_runs(tape, read(folder / "capture.json")["runs"], seed, count)
    iface = Interfaces(read(folder / "program.json"))
    store = Store(iface, rename_seed)
    wanted = defaultdict(dict)
    classes = {}
    for q in tape["requests"]:
        if q["run"] in runs:
            keys = tuple(
                (store.alias(p["address"]["token"]), p["address"]["op"])
                for p in q["parents"]
            )
            wanted[q["run"], q["rule"]][keys] = q["token"]
    stats = Counter()
    with (folder / "memory.jsonl").open() as f:
        for frame in map(json.loads, f):
            store.advance(frame)
            run = frame["run"]
            if run not in runs:
                continue
            for rid, wm in frame["rules"]:
                truth = wanted[run, rid]
                for keys, token in truth.items():
                    classes[token] = (
                        iface.key(rid, keys, store.types),
                        len({t for t, _ in keys}),
                    )
                roles = iface.roles[rid]
                if not roles or any(
                    not store.by_table[iface.tables.index(t)] for t, _ in roles
                ):
                    continue
                fresh = lambda row: min(
                    (
                        role
                        for role, k in row
                        if not iface.rules[rid]["metadata"]["seminaive"]
                        or store.visible[k]["version"] >= wm
                    ),
                    default=10000,
                )
                teacher_layouts = Counter(
                    tuple(i for i, (owner, _) in enumerate(keys) if owner == keys[0][0])
                    for keys in truth
                    if keys and len({t for t, _ in keys}) <= 2
                )
                projections = {}
                for left, right in iface.layouts(rid):
                    for side in (left, right):
                        if side and side not in projections:
                            projections[side] = store.projections(rid, side)
                    a = projections[left]
                    b = projections[right] if right else [()]
                    if a is None or b is None or len(a) * len(b) > 65536:
                        stats["over_budget_layouts"] += 1
                        stats["canonical_at_layout_cap"] += teacher_layouts[left]
                        continue
                    if not a or not b:
                        continue
                    fa = [fresh(zip(left, x)) for x in a]
                    fb = [fresh(zip(right, x)) for x in b]
                    if min(fa + fb) >= 10000:
                        continue
                    xa = encode(store, rid, left, a, wm, right)
                    xb = encode(store, rid, right, b, wm, left) if right else None
                    for flip in range(2 if right else 1):
                        aa, bb = (b, a) if flip else (a, b)
                        ff, gg = (fb, fa) if flip else (fa, fb)
                        la, lb = (right, left) if flip else (left, right)
                        for i, row in enumerate(aa):
                            if ff[i] >= 10000:
                                continue
                            ix = [
                                j
                                for j, other in enumerate(bb)
                                if not other
                                or (other[0][0] != row[0][0] and ff[i] < gg[j])
                            ]
                            if not ix:
                                continue
                            keys = []
                            for j in ix:
                                full = [None] * len(roles)
                                for col, k in zip(la, row):
                                    full[col] = k
                                for col, k in zip(lb, bb[j]):
                                    full[col] = k
                                keys.append(tuple(full))
                            x, y = (xb, xa) if flip else (xa, xb)
                            visit(
                                run,
                                rid,
                                store,
                                keys,
                                truth,
                                [z[i : i + 1] for z in x],
                                [z[ix] for z in y] if y else None,
                                flip,
                            )
                            stats["events"] += 1
                            stats["candidates"] += len(keys)
    return runs, classes, stats


def request(run, rid, keys, store):
    return dict(
        run=run,
        rule=rid,
        parents=[
            dict(
                address=dict(token=store.original.get(t, t), op=pc),
                version=store.visible[t, pc]["version"],
            )
            for t, pc in keys
        ],
    )
