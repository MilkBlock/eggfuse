"""Frozen selection of Higher Cell layouts by training frequency or downstream owner reduction."""

import argparse
import json
from collections import Counter, defaultdict
from heapq import heapify, heappop, heappush
from pathlib import Path

from higher_cell import read
from ripsat_layout import capture
from ripsat_replay import unpack


def cases(folder, donor, depth):
    refs, _, groups, _ = capture(
        folder, donor, depth, each_parent_first=True, grow_consumers=True
    )
    occurrences = defaultdict(set)
    for layouts in groups.values():
        for layout, rows in layouts.items():
            for _, ready, scheduled, tokens in rows:
                if ready and scheduled:
                    occurrences[layout].add(tokens)
    return refs, occurrences


def owners(q):
    return {p["address"]["token"] for p in q["parents"]}


def train(root, donor, depth):
    frequency = Counter()
    benefit = defaultdict(dict)
    for name in ("sum", "dot"):
        refs, occ = cases(root / name, donor, depth)
        by_id = {q["token"]: q for q in refs}
        uses = defaultdict(set)
        for q in refs:
            parents = owners(q)
            if len(parents) > 2:
                for parent in parents:
                    uses[parent].add(q["token"])
        for layout, groups in occ.items():
            frequency[layout] += len(groups)
            for g in groups:
                end = max(by_id[t]["run"] for t in g)
                for child, n in Counter(c for t in g for c in uses[t]).items():
                    if n > 1 and by_id[child]["run"] > end:
                        k = name, child
                        benefit[layout][k] = max(benefit[layout].get(k, 0), n - 1)
    popular = sorted(frequency, key=lambda k: (-frequency[k], k))
    # Greedy marginal increase of the best single-package owner reduction per consumer.
    queue = [(-sum(g.values()), -frequency[k], k) for k, g in benefit.items()]
    heapify(queue)
    best = Counter()
    rank = []
    while queue and len(rank) < 4096:
        neg, tie, k = heappop(queue)
        g = benefit[k]
        gain = sum(max(0, n - best[c]) for c, n in g.items())
        if not gain:
            continue
        if gain < -neg:
            heappush(queue, (-gain, tie, k))
            continue
        rank.append(k)
        for c, n in g.items():
            best[c] = max(best[c], n)
    chosen = set(rank)
    return popular, rank + [k for k in popular if k not in chosen], len(rank)


def pack(refs, occ, catalog, targets):
    ends = {q["token"]: q["run"] for q in refs}
    groups = sorted(
        (
            (max(ends[t] for t in g), -len(g), g, k)
            for k in catalog
            for g in occ.get(k, ())
        ),
        key=lambda x: x[:3],
    )
    used = {}
    active = set()
    instances = 0
    for end, _, g, k in groups:
        if any(t in used for t in g):
            continue
        for t in g:
            used[t] = (g[0], end)
        instances += 1
        active.add(k)
    hist = Counter()
    saved = 0
    all_low = 0
    units = defaultdict(set)
    by_token = {q["token"]: q for q in refs}
    for token, (rep, _) in used.items():
        units[rep].add(token)
    boundary_counts = Counter()
    for target in targets:
        group = units[used[target][0]] if target in used else {target}
        start = min(ends[t] for t in group)
        ext = set().union(*(owners(by_token[t]) for t in group)) - group
        boundary = {used[t][0] if t in used and used[t][1] < start else t for t in ext}
        boundary_counts[len(boundary)] += 1
    for q in refs:
        ps = owners(q)
        count = len(
            {used[t][0] if t in used and used[t][1] < q["run"] else t for t in ps}
        )
        all_low += 1 <= count <= 2
        if q["token"] in targets:
            hist[count] += 1
            saved += len(ps) - count
    return dict(
        targets=len(targets),
        became_low=hist[1] + hist[2],
        external_parents_saved=saved,
        after=hist,
        unit_boundary=boundary_counts,
        unit_low=sum(v for n, v in boundary_counts.items() if n <= 2),
        all_low=all_low,
        instances=instances,
        used_layouts=len(active),
        catalog_size=len(catalog),
    )


def study(root):
    base = unpack(read(root / "unified-scale/baked/catalog.json"))
    depth = max(map(len, base))
    donor = read(root / "sum/program.json")
    pop, greedy, n = train(root, donor, depth)
    results = {}
    for w in ("fact", "loopfact", "sum-divisors"):
        refs, occ = cases(root / w, donor, depth)
        targets = set(
            read(
                Path(__file__).parent
                / "run-recall/shared-composition"
                / f"{w}-higher.json"
            )["negative_ids"]
        )
        results[w] = {"frozen": pack(refs, occ, base, targets)}
        for size in (64, 4096):
            for name, rank in [
                ("frequency", pop),
                (
                    "chain_frequency",
                    [
                        k
                        for k in pop
                        if all(
                            {u for u, _ in step[2] if u >= 0} == {i - 1}
                            for i, step in enumerate(k)
                            if i
                        )
                    ],
                ),
                ("greedy", greedy),
            ]:
                results[w][f"{name}_{size}"] = pack(refs, occ, rank[:size], targets)
    return dict(
        track="Neural Compilation",
        mode="offline heuristic controls",
        depth=depth,
        training_layouts=len(pop),
        greedy_positive=n,
        cases=results,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    a.output.write_text(json.dumps(study(a.root), indent=2) + "\n")
