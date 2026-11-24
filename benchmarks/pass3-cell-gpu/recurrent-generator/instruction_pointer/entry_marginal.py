"""Measure marginal B visits of signed paths without scoring their unrelated siblings.
Applies to B with independent per-prefix scores, a fixed event and frozen snapshot.
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import numpy as np
import torch

from cell_stream import CellStream
from entry_closure import named
from event_addresses import Directory
from receipt_bake import read, save
from recursive_rollout import get_policy


@torch.no_grad()
def path_costs(data, d, children):
    costs = {t: Counter() for t in children}
    packets = defaultdict(list)
    for q in read(d / "tape.json")["requests"]:
        if q["token"] in children:
            packets[q["run"]].append(q)
    pol = get_policy(data, d, "free", "multi")
    rd, model = pol.reader, pol.model
    mem = Directory(rd, Counter())
    for frame in map(json.loads, (d / "memory.jsonl").open()):
        rd.advance(frame)
        rules = dict(frame["rules"])
        jobs = defaultdict(set)
        for q in packets[frame["run"]]:
            r = q["rule"]
            refs = tuple(map(named, q["parents"]))
            for j, (_, _, v) in enumerate(refs):
                if v >= rules[r]:
                    jobs[r, j].add((q["token"], refs))
        for (r, j), rows in jobs.items():
            if len(mem.roles[r]) == 1:
                for t, _ in rows:
                    costs[t].update(["unary_event_skips", "suppressed_b_proposals"])
                continue
            order = mem.order(r, j)
            ptr = CellStream(
                rd,
                model,
                r,
                rules[r],
                mem.stats,
                order=order,
                role_ports=lambda t: mem.bank(t).ports,
            )
            ptr.prepare()
            tokens, refs = zip(*sorted(rows))
            tokens = np.asarray(tokens)
            paths = np.array(
                [
                    [
                        mem.bank(mem.roles[r][role]).positions[row[role][:2]]
                        for role in order
                    ]
                    for row in refs
                ]
            )
            h = model.start(rd.meta(r)).expand(len(paths), -1)
            _, h = ptr.logits(h, 0, torch.from_numpy(paths[:, :1]))
            for depth in range(1, len(order)):
                post, start, count = mem.window(
                    r, order[:depth], order[depth], paths[:, :depth]
                )
                if post is not None:
                    keep = []
                    for i, (k, lo, n) in enumerate(zip(paths[:, depth], start, count)):
                        pos = lo + np.searchsorted(post[lo : lo + n], k)
                        if pos < lo + n and post[pos] == k:
                            keep.append(i)
                    paths = paths[keep]
                    tokens = tokens[keep]
                    h = h[keep]
                if not len(paths):
                    break
                if depth + 1 == len(order):
                    for t in tokens:
                        costs[t]["removed_terminal_visits"] += 1
                logits, h = ptr.logits(
                    h, depth, torch.from_numpy(paths[:, : depth + 1])
                )
                ok = logits >= 0
                paths = paths[ok.numpy()]
                tokens = tokens[ok.numpy()]
                h = h[ok]
                if depth + 1 == len(order):
                    for t in tokens:
                        costs[t]["suppressed_b_proposals"] += 1
                if not len(paths):
                    break
    return costs


def marginal(data, source, out, name):
    d = source / name
    proof = read(out / (name + "-oracle.json"))
    if not all(proof["native"]["checks"].values()):
        raise ValueError("unverified pack")
    children = {t for _, ts in proof["packed"] for t in ts[1:]}
    stats = Counter()
    for cost in path_costs(data, d, children).values():
        stats.update(cost)
    result = dict(
        scope="conditional marginal on native-verified covered paths and fresh root roles",
        counts=stats,
    )
    full = out / (name + "-search.json")
    if full.exists():
        a = read(full)
        if stats["suppressed_b_proposals"] != a["removed_b_proposals"] or stats[
            "removed_terminal_visits"
        ] != a["control"].get("visits", 0) - a["specialized"].get("visits", 0):
            raise ValueError(("marginal differs from exhaustive decoder", stats, a))
        result["full_stream_equivalence"] = True
    save(out / (name + "-marginal.json"), result)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("data", "source", "out"):
        p.add_argument(k, type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    torch.set_num_threads(1)
    with torch.no_grad():
        for name in a.cases:
            marginal(a.data, a.source, a.out, name)
