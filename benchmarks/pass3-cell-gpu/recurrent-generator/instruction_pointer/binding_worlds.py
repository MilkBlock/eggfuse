"""Native, reproducible fresh-filler worlds. Only the offline fork supplies labels."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import random
from tempfile import TemporaryDirectory
from shutil import copyfile

from completion_context import cmd, native, read, write, SIZES

# Each link is (earlier atom, column, later atom, column).
TRAIN = {
    "eq01": [(0, 0, 1, 1)],
    "eq12": [(0, 1, 1, 2)],
    "eq20": [(0, 2, 1, 0)],
    "joint": [(0, 0, 1, 1), (0, 1, 1, 2)],
    "three": [(0, 0, 1, 1), (1, 0, 2, 2)],
}
UNSEEN = {
    "eq10": [(0, 1, 1, 0)],
    "eq21": [(0, 2, 1, 1)],
    "eq02": [(0, 0, 1, 2)],
    "two": [(0, 1, 1, 2), (0, 2, 1, 0)],
    "chain": [(0, 1, 1, 0), (1, 1, 2, 0)],
    "four": [(0, 1, 1, 0), (1, 1, 2, 0), (2, 1, 3, 0)],
    "guard": [(0, 1, 1, 0)],
    "merge": [(0, 1, 1, 0)],
}
LAYOUTS = TRAIN | UNSEEN


def source(
    index,
    n,
    layout,
    order,
    typed=False,
    partial=False,
    edge_limit=None,
    cross_guard=False,
    completed_count=None,
):
    links = LAYOUTS[layout]
    k = max(r for _, _, r, _ in links) + 1
    rng = random.Random(199933 + index)
    slots = [list(range(i * 3, i * 3 + 3)) for i in range(k)]
    for p, c, q, b in links:
        slots[q][b] = slots[p][c]
    names = {
        j: "v" + str(v) for j, v in zip(range(k * 3), rng.sample(range(100000), k * 3))
    }
    # Disjoint signed 64-bit filler ranges, independent of names and placement.
    fresh = iter(rng.sample(range(1 << 24), 4 * n + 100))

    def value():
        return (index + 1) * (1 << 26) + next(fresh)

    rows = []
    targets = []
    reps = 1 if n < 8 else 1 + index % min(4, n // (2 * k))
    if edge_limit is not None:
        reps = 1
    if cross_guard:
        reps = 2
    used = sorted({j for s in slots for j in s})
    loose = [j for j in used if sum(s.count(j) for s in slots) == 1]
    for rep in range(reps):
        vals = {j: value() for j in used}
        if layout == "guard":
            a, b = (loose[0], loose[-1]) if cross_guard else loose[:2]
            vals[a], vals[b] = sorted((vals[a], vals[b]), reverse=bool(rep % 2))
        targets.append([vals[j] for j in used])
        rows.extend(("Edge", [vals[j] for j in ss]) for ss in slots)
    # One-field near matches for the conjunction.
    while len(rows) < n:
        v = [value() for _ in range(3)]
        if len(links) > 1 and k == 2:
            _, a, _, b = links[len(rows) % 2]
            v[b] = rows[0][1][a]
        rows.append(
            (
                "Noise"
                if typed or (edge_limit is not None and len(rows) >= edge_limit)
                else "Edge",
                v,
            )
        )
    sort = " ".join(["i64"] * len(used))
    body = [
        "(relation Edge (i64 i64 i64))",
        "(relation Noise (i64 i64 i64))",
        f"(relation Result ({sort}))",
        "(ruleset warm)",
        "(ruleset probe)",
    ]
    out = " ".join(names[j] for j in used)
    atoms = " ".join("(Edge " + " ".join(names[j] for j in s) + ")" for s in slots)
    if layout == "guard":
        atoms += (
            f" (< {names[loose[0]]} {names[loose[-1] if cross_guard else loose[1]]})"
        )
    if layout == "merge":
        # Updated mutable field is a parent of the actual rule. Reads carry the published version.
        body += [
            "(function Price (i64) i64 :merge (min old new))",
            "(relation Update (i64 i64))",
            "(rule ((Update a b)) ((set (Price a) b)) :ruleset warm)",
        ]
        for t in targets:
            x = t[used.index(slots[0][1])]
            body += [f"(set (Price {x}) 9223372036854775807)", f"(Update {x} {x})"]
        atoms += f" (= (Price {names[slots[0][1]]}) {names[slots[0][1]]})"
    if partial:
        body += [
            f"(relation Done ({sort}))",
            f"(rule ((Done {out})) ((Result {out})) :ruleset warm)",
        ]
        done = (
            targets[:-1]
            if completed_count is None
            else random.Random(7127 + index).sample(targets, completed_count)
        )
        for t in done:
            body.append("(Done " + " ".join(map(str, t)) + ")")
    body += [f"(rule ({atoms}) ((Result {out})) :ruleset probe)"]
    random.Random(10733 * order + index + 73).shuffle(rows)
    for table, vals in rows:
        body.append("(" + table + " " + " ".join(map(str, vals)) + ")")
    return "\n".join(body + ["(run-schedule (run warm) (run probe))"]) + "\n"


def jobs(count):
    train_names = list(TRAIN)
    for i in range(count):
        yield (
            "train",
            i,
            (4, 8, 16, 8)[(i // 5) % 4],
            train_names[i % 5],
            i % 2,
            False,
            i % 7 == 0,
        )
    for done in range(4):
        for i in range(4):
            for order in (0, 1):
                yield f"subset-{done}", 72003 + 4 * i, 16, "eq10", order, False, True
    for i in range(12):
        for order in (0, 1):
            yield "cross-guard", 50000 + i, 4, "guard", order, False, False
    for limit in (4, 8, 16, 32, 64):
        for i in range(8):
            for p in (0, 1):
                yield f"density-{limit}", 40000 + i, 64, "eq10", p, False, False
    for n in SIZES:
        for j, layout in enumerate(UNSEEN):
            for i in range(8 if n <= 16 else 3):
                for p in range(2):
                    yield "test", 20000 + i + 100 * j, n, layout, p, False, False
        for i in range(3):
            for p in range(2):
                yield "noise", 30000 + i, n, "eq10", p, True, False


def build(a, job, *, override=None):
    split, i, n, layout, p, typed, partial = job
    d = a.out / "worlds" / split / f"{n:04}-{layout}-{i:05}-{p}"
    if (d / "ok.json").exists():
        return
    d.mkdir(parents=True, exist_ok=True)
    (d / "world.egg").write_text(
        source(
            i,
            n,
            layout,
            p,
            typed,
            partial,
            int(split.split("-")[1]) if split.startswith("density-") else None,
            cross_guard=split == "cross-guard",
            completed_count=int(split[7:]) if split.startswith("subset-") else None,
        )
        if override is None
        else override
    )
    with TemporaryDirectory() as t:
        cmd(
            [
                a.compiler,
                "compile",
                "--source",
                d / "world.egg",
                "--output",
                Path(t) / "ir",
            ]
        )
        copyfile(Path(t) / "ir/program.json", d / "program.json")
    native(a, d, "capture", d / "teacher.json", "--address-seed", 73007 + i * 32771 + p)
    tape = read(d / "teacher.json")
    warm = [q for q in tape["requests"] if q["run"] == 1]
    write(d / "prefix.json", dict(tape, requests=warm))
    gold = [q for q in tape["requests"] if q["run"] == 2]
    rep = native(
        a,
        d,
        "replay",
        d / "teacher.json",
        2,
        "--memory",
        d / "frames.jsonl",
        "--ept-origins",
        env=dict(os.environ, EGGFUSE_QUERY_OBSERVER=str(d / "observer.jsonl")),
    )
    gains = dict(rep["ept"]["origins"])
    if rep["counts"]["accepted"] < len(gold) or any(
        gains.get(q["token"], 0) > 1 for q in gold
    ):
        raise ValueError((d, rep["counts"]))
    gold = [q for q in gold if gains.get(q["token"], 0) == 1]
    if not gold:
        raise ValueError(f"no new target {d}")
    write(
        d / "ok.json",
        dict(
            instance=i,
            size=n,
            layout=layout,
            order=p,
            typed=typed,
            split=split,
            partial=partial,
            warm=len(warm),
            gold=gold,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--compiler", type=Path, required=True)
    p.add_argument("--runtime-binary", type=Path, required=True)
    p.add_argument("--count", type=int, default=4096)
    p.add_argument("--workers", type=int, default=8)
    a = p.parse_args()
    with ThreadPoolExecutor(a.workers) as pool:
        for j, _ in enumerate(pool.map(lambda x: build(a, x), jobs(a.count))):
            if j % 500 == 0:
                print(j, flush=True)
