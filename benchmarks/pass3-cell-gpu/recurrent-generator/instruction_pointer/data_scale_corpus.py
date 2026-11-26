"""Generate distinct staged Recipe DAGs and replay witnessed multi-token target plans."""

import argparse
import hashlib
import json
import random
import subprocess
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from recursive_train import binary, read


def program(seed):
    rng = random.Random(seed)
    inputs = rng.randint(2, 5)
    count = rng.randint(48, 64)
    stages = rng.randint(3, 6)
    levels = [list(range(inputs))]
    tables = inputs
    graph = []
    lines = []
    facts = []
    for i in range(inputs):
        for x in range(count):
            if i == 0 or rng.random() > 0.08:
                facts.append(f"(P{i:03d} {x})")
    for stage in range(stages):
        level = []
        for _ in range(rng.randint(5, 10)):
            first = rng.choice(levels[-1])
            other = [i for level in levels for i in level if i != first]
            deps = [first, *rng.sample(other, rng.randint(0, min(2, len(other))))]
            threshold = rng.choice([None, None, None, count // 2])
            body = " ".join(f"(P{i:03d} x)" for i in deps)
            if threshold is not None:
                body += f" (< x {threshold})"
            lines.append(f"(rule ({body}) ((P{tables:03d} x)) :ruleset s{stage})")
            graph.append((stage, deps, threshold is not None))
            level.append(tables)
            tables += 1
        levels.append(level)
    source = [
        *(f"(relation P{i:03d} (i64))" for i in range(tables)),
        *(f"(ruleset s{i})" for i in range(stages)),
        *lines,
        *facts,
        "(run-schedule " + " ".join(f"(run s{i})" for i in range(stages)) + ")",
    ]
    sig = hashlib.sha256(json.dumps([inputs, graph]).encode()).hexdigest()
    return "\n".join(source) + "\n", sig


def native(args):
    return json.loads(subprocess.check_output([str(v) for v in args]))


def build(a, index):
    d = a.out / "programs" / f"{index:04d}"
    d.mkdir(exist_ok=True, parents=True)
    source, sig = program(index + 71391)
    egg = d / "source.egg"
    egg.write_text(source)
    with TemporaryDirectory(dir=d) as tmp:
        compiled = Path(tmp) / "compiled"
        subprocess.run(
            [a.compiler, "compile", "--source", egg, "--output", compiled],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        (compiled / "program.json").replace(d / "program.json")
    runtime = binary(a.data)
    p = d / "program.json"
    tp = d / "teacher.json"
    cap = native(
        [runtime, "capture", p, tp, "time", "--memory", d / "memory.jsonl", "--ept"]
    )
    tape = read(tp)
    replay = native([runtime, "replay", p, tp, "time", "--ept-origins"])
    requests = tape["requests"]
    if (
        replay["counts"]["accepted"] != len(requests)
        or cap["state_sha"] != replay["state_sha"]
    ):
        raise ValueError("reference/receiver disagreement")
    gains = dict(replay["ept"]["origins"])
    by_run = defaultdict(list)
    for i, q in enumerate(requests):
        if gains.get(q["token"], 0) > 0:
            by_run[q["run"]].append(i)
    last = max(by_run)
    chosen = by_run[last].copy()
    rng = random.Random(index + 3731)
    rng.shuffle(chosen)
    chosen = chosen[: max(1, len(chosen) * 3 // 4)]
    prefix = [q for q in requests if q["run"] < last]
    # No future consumer of these final-Run tokens. Their parents remain unchanged.
    counter = [
        dict(requests[i], token=len(prefix) + j + 1) for j, i in enumerate(chosen)
    ]
    cp = d / "counter.json"
    cp.write_text(json.dumps(dict(tape, requests=prefix + counter)))
    cf = native([runtime, "replay", p, cp, "time", "--ept-origins"])
    credited = dict(cf["ept"]["origins"])
    if cf["counts"]["accepted"] != len(prefix) + len(counter) or any(
        credited.get(q["token"], 0) <= 0 for q in counter
    ):
        raise ValueError("counterfactual not witnessed")
    windows = []
    seen = set()
    for run, seq in [*by_run.items(), (last, chosen)]:
        for j in range(len(seq)):
            for width in range(1, min(j + 1, 4) + 1):
                ids = tuple(seq[j - width + 1 : j + 1])
                if ids not in seen:
                    seen.add(ids)
                    windows.append([run, *ids, *([-1] * (4 - width))])
    rng.shuffle(windows)
    np.save(d / "plans.npy", np.array(windows, dtype=np.int32))
    meta = {
        "id": index,
        "signature": sig,
        "requests": len(requests),
        "plans": len(windows),
        "runs": len(by_run),
        "counter_accepted": len(counter),
        "reference": cap["state_sha"],
        "counter": cf["state_sha"],
    }
    (d / "verified.json").write_text(json.dumps(meta) + "\n")
    return meta


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--data", type=Path, default=Path("/tmp/dfm-local/data"))
    a.add_argument(
        "--compiler",
        type=Path,
        default=Path("/tmp/cost-audit-build/release/eggfuse-cell-compiler"),
    )
    a.add_argument("--limit", type=int, default=1_000_000)
    a.add_argument("--first", type=int, default=0)
    a.add_argument(
        "--programs",
        type=int,
        help="Build this number of programs instead of stopping at a plan count",
    )
    opt = a.parse_args()
    total = 0
    records = []
    while (
        len(records) < opt.programs if opt.programs is not None else total < opt.limit
    ):
        i = opt.first + len(records)
        path = opt.out / "programs" / f"{i:04d}" / "verified.json"
        rec = read(path) if path.exists() else build(opt, i)
        if any(r["signature"] == rec["signature"] for r in records):
            raise ValueError("duplicate Recipe DAG")
        records.append(rec)
        total += rec["plans"]
        if i % 20 == 0:
            print(i, total, flush=True)
    (opt.out / "corpus.json").write_text(json.dumps(records) + "\n")


if __name__ == "__main__":
    main()
