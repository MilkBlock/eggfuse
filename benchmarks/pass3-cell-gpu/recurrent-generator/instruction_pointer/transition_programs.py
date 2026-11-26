"""Native training environments with a repeated schedule and mutable facts."""

import argparse
import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from credit_scale_programs import split_check
from data_scale_corpus import program


def source(index):
    original, signature = program(71391 + index)
    body, _ = original.rsplit("(run-schedule ", 1)
    stages = re.findall(r"^\(ruleset (s\d+)\)", body, re.MULTILINE)
    last = re.findall(r"\(\(P(\d+) x\)\) :ruleset", body)[-1]
    # The same immutable operand can drive two writes with different marginal effects.
    extra = f"""
(datatype Item (Key i64) (Wrap Item))
(function price (Item) i64 :merge (min old new))
(relation Memo (i64))
(relation Seen (i64))
(ruleset publish)
(ruleset lower)
(ruleset repair)
(ruleset clear)
(rule ((P000 x)) ((set (price (Key x)) 20) (Memo x)) :ruleset publish)
(rule ((P001 x)) ((Memo x)) :ruleset s0)
(rule ((= v (price (Key x)))) ((Seen v)) :ruleset publish)
(rule ((P{last} x)) ((set (price (Key x)) 1)) :ruleset lower)
(rule ((P000 x) (< x 8)) ((set (price (Key x)) 3)) :ruleset lower)
(rule ((= a (Key 0)) (= b (Key 1))) ((union a b)) :ruleset repair)
(rule ((P000 x) (< x 4)) ((delete (Memo x))) :ruleset clear)
(Wrap (Key 0)) (Wrap (Key 1))
(set (price (Key 0)) 90) (set (price (Key 1)) 80)
"""
    # Fresh P000 rows reactivate its consumers after an idle revisit.
    extra += f"(rule ((P{last} x) (< x 8)) ((P000 (+ x 100))) :ruleset lower)\n"
    if index >= 32:
        extra += """
(datatype Label (Mark i64) (Combined Label Label))
(function labels (Item) Label :merge (Combined old new))
(set (labels (Key 0)) (Mark 0)) (set (labels (Key 1)) (Mark 1))
(rule () ((union (Key 0) (Key 1))) :ruleset repair)
(rule ((= k (Combined a b))) ((Seen 7)) :ruleset publish)
"""
    schedule = [
        "publish",
        *stages,
        "publish",
        *stages,
        "clear",
        "lower",
        "repair",
        "publish",
        "publish",
        *stages,
        "lower",
        "publish",
    ]
    text = (
        body
        + extra
        + "(run-schedule "
        + " ".join(f"(run {s})" for s in schedule)
        + ")\n"
    )
    return text, signature


def prepare(a):
    records = []
    split_check(a.prior, range(a.first, a.count))

    def one(i):
        d = a.out / "dynamic" / "programs" / f"{i:04d}"
        d.mkdir(parents=True, exist_ok=True)
        text, sig = source(i)
        path = d / "source.egg"
        if path.exists() and path.read_text() != text:
            raise ValueError(f"training source changed at {i}")
        path.write_text(text)
        ir = d / "program.json"
        if not ir.exists():
            with TemporaryDirectory(dir=d) as tmp:
                output = Path(tmp) / "ir"
                subprocess.run(
                    [a.compiler, "compile", "--source", path, "--output", output],
                    check=True,
                    stdout=subprocess.DEVNULL,
                )
                (output / "program.json").replace(ir)
        return {
            "id": i,
            "signature": sig,
            "source_sha": hashlib.sha256(text.encode()).hexdigest(),
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(one, range(a.first, a.count)))
    path = a.out / "dynamic" / "corpus.json"
    old = {v["id"]: v for v in json.loads(path.read_text())} if path.exists() else {}
    old.update({v["id"]: v for v in records})
    signatures = split_check(a.prior, old)
    if len(set(signatures.values())) != len(signatures):
        raise ValueError("duplicate normalized graph")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps([old[i] for i in sorted(old)]) + "\n")
    tmp.replace(path)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--first", type=int, default=0)
    p.add_argument("--count", type=int, required=True)
    for arg in ("prior", "out", "compiler"):
        p.add_argument("--" + arg, required=True, type=Path)
    prepare(p.parse_args())
