"""Paired B decoder on actual named root events from native-verified packings.
Both arms measure the identical teacher snapshot and delta event; no wake/teacher
predictions enter an independent rollout. Uncovered proposal multisets must agree.
"""

from argparse import ArgumentParser
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
import torch

from entry_rollout import Entries
from entry_closure import named
from event_addresses import Directory
from event_generator import EventGenerator
from recursive_rollout import get_policy
from receipt_bake import read, save


class Sink(Entries):
    def __init__(self, covered, reference):
        self.covered_rules = covered
        self.covered_indices = {}
        self.residual = defaultdict(hashlib.sha256)
        self.advertised = Counter()
        self.reference = {}
        for r, tuples in reference.items():
            a = np.asarray(list(tuples), dtype=np.int64)
            self.reference[r] = self.records(a) if a.size else None

    @staticmethod
    def records(a):
        a = np.ascontiguousarray(a)
        return (
            a.reshape(len(a), -1)
            .view(np.dtype((np.void, a.dtype.itemsize * a.shape[1] * a.shape[2])))
            .reshape(-1)
        )

    def start(self, rd, pub, txn, rules, stats):
        self.count = stats

    def choose(self, *args):
        pass

    def issue(self, r, roots, refs, txn):
        covered = self.reference[r]
        known = (
            np.ones(len(refs), bool)
            if covered is None
            else np.isin(self.records(refs), covered)
        )
        self.advertised[r] += int(known.sum())
        self.residual[r].update(refs[~known].tobytes())


class Events:
    def __init__(self, events):
        self.events = events

    def emit(self, mem, rules, model, cuts, stats):
        for (r, j), positions in sorted(self.events.items()):
            yield r, j, np.array(sorted(positions), dtype=np.int64)


def probe(data, source, out, name):
    d = source / name
    # Only packings that have passed native full-trajectory checks enter here.
    oracle = read(out / (name + "-oracle.json"))
    if not all(oracle["native"]["checks"].values()):
        raise ValueError("incomplete replay")
    selected = {t for _, ts in oracle["packed"] for t in ts[1:]}
    runs = defaultdict(list)
    for q in read(d / "tape.json")["requests"]:
        if q["token"] in selected:
            runs[q["run"]].append(q)
    policy = get_policy(data, d, "free", "multi")
    rd = policy.reader
    counts = [Counter(), Counter()]
    event_source = Directory(rd, Counter())
    gens = [
        EventGenerator(data, name, Path("run-recall/cell-events"), "B") for _ in counts
    ]
    for g, c in zip(gens, counts):
        g.memory = Directory(rd, c)
    summary = Counter()
    for f in map(json.loads, (d / "memory.jsonl").open()):
        rd.advance(f)
        if f["run"] not in runs:
            continue
        rules = dict(f["rules"])
        covered = defaultdict(set)
        events = defaultdict(set)
        for q in runs[f["run"]]:
            r = q["rule"]
            parents = tuple(map(named, q["parents"]))
            covered[r].add(parents)
            for j, (t, op, v) in enumerate(parents):
                if v >= rules[r]:
                    events[r, j].add(
                        event_source.bank(event_source.roles[r][j]).positions[t, op]
                    )
            if not parents:
                events[r, -1].add(0)
        results = []
        for g, c, done in zip(gens, counts, ({}, covered)):
            g.waiting.clear()
            g.higher = Sink(done, covered)
            g.tree = Events(events)
            g.run_snapshot(f, None, rd, policy.model, None, c, float("inf"))
            results.append(g.higher)
        for rid in covered:
            if results[0].residual[rid].digest() != results[1].residual[rid].digest():
                raise ValueError("uncovered proposal stream changed")
        summary["removed_b_proposals"] += (
            results[0].advertised.total() - results[1].advertised.total()
        )
        summary["root_events"] += sum(map(len, events.values()))
    save(
        out / (name + "-search.json"),
        dict(
            scope="given delta roots of native-replayed children",
            **summary,
            oracle_event_lookup=event_source.stats,
            control=counts[0],
            specialized=counts[1],
        ),
    )


if __name__ == "__main__":
    p = ArgumentParser()
    for k in ("data", "source", "out"):
        p.add_argument(k, type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    torch.set_num_threads(1)
    with torch.no_grad():
        for name in a.cases:
            probe(a.data, a.source, a.out, name)
