"""Check full topology signatures before compiling or perturbing a new training graph."""

import argparse
import hashlib
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from data_scale_corpus import build, program
from discovery_states import save
from recursive_train import read


def directory(a, idx):
    base = a.previous / "programs" / f"{idx:04d}"
    return base if base.is_dir() else a.out / "novel" / "programs" / f"{idx:04d}"


def topology(source):
    """Name-independent signature for this corpus grammar. Ambiguities group splits conservatively."""
    colors = {}
    consumers = Counter()
    nodes = []
    for line in source.splitlines():
        if not line.startswith("(rule "):
            continue
        ids = re.findall(r"\(P(\d+) x\)", line)
        parents, head = ids[:-1], ids[-1]
        stage = int(re.search(r":ruleset s(\d+)", line)[1])
        inputs = sorted(colors.get(parent, "entry") for parent in parents)
        label = hashlib.sha256(
            repr((stage, inputs, "(< " in line)).encode()
        ).hexdigest()
        if head in colors:
            raise ValueError("expected one producer per derived table")
        colors[head] = label
        nodes.append(label)
        consumers.update(parents)
    degrees = sorted((colors.get(k, "entry"), n) for k, n in consumers.items())
    return hashlib.sha256(repr((sorted(nodes), degrees)).encode()).hexdigest()


def split_check(previous, indices):
    held = read(previous / "held" / "corpus.json")
    held_signatures = {topology(program(71391 + p["id"])[0]) for p in held}
    result = {i: topology(program(71391 + i)[0]) for i in indices}
    if held_signatures.intersection(result.values()):
        raise ValueError("name-independent structure crosses the split")
    return result


def prepare(a):
    held = {p["signature"] for p in read(a.previous / "held" / "corpus.json")}
    known = {p["signature"] for p in read(a.previous / "corpus.json")}
    if known & held:
        raise ValueError("existing split overlap")
    ids = list(range(a.first, a.stop))
    split_check(a.previous, ids + [p["id"] for p in read(a.previous / "corpus.json")])
    for i in ids:
        _, sig = program(71391 + i)
        if sig in held | known:
            raise ValueError("train/held topology collision")
        known.add(sig)
    cfg = SimpleNamespace(out=a.out / "novel", data=a.data, compiler=a.compiler)

    def one(i):
        ver = cfg.out / "programs" / f"{i:04d}" / "verified.json"
        return read(ver) if ver.exists() else build(cfg, i)

    with ThreadPoolExecutor(max_workers=4) as workers:
        manifest = list(workers.map(one, ids))
    save(cfg.out / "corpus.json", manifest)
    print("compiled", len(ids), "distinct training DAGs")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("out", "previous", "data", "compiler"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--first", type=int, default=210)
    p.add_argument("--stop", type=int, default=480)
    prepare(p.parse_args())
