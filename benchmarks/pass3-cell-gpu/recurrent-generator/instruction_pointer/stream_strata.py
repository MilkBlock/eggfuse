"""Frozen reference-stratum recognition versus actual exhaustive generation."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter

import torch

from anchor_set_audit import check
from cell_stream import CellStream
from recursive_rollout import get_policy
from recursive_train import binary, folder, keys, read
from relation_cases import request


@torch.no_grad()
def audit(root, case, seconds):
    base = Path(__file__).parent / "run-recall"
    d = folder(root, case)
    tape = read(d / "tape.json")
    high = set(
        read(base / "shared-composition" / (case + "-higher.json"))["negative_ids"]
    )
    first = {
        x["token"]
        for x in read(base / "oracle-headroom/divergence.json")[case]["missing"]
    }
    targets = defaultdict(lambda: defaultdict(list))
    for q in tape["requests"]:
        if q["token"] in high | first:
            targets[q["run"]][q["rule"]].append(q)
    policy = get_policy(root, d, "free", "multi")
    rd = policy.reader
    emitted = []
    passing = set()
    counts = Counter()
    records = []
    for f in map(json.loads, (d / "memory.jsonl").open()):
        rd.advance(f)
        wms = dict(f["rules"])
        for r, qs in targets[f["run"]].items():
            a = CellStream(rd, policy.model, r, wms[r], counts)
            paths = [tuple(keys(q)[j] for j in a.order) for q in qs]
            lookup = {p: q for p, q in zip(paths, qs, strict=True)}
            expected = {
                q["token"] for q, ok in zip(qs, a.named(paths, 0), strict=True) if ok
            }
            passing.update(expected)
            # All typed branches are reachable. Chunk scheduling consumes no label.
            # A per-stratum wall guard censors this diagnostic, never the recognition test.
            found = set()
            total = 0
            done = True
            t = perf_counter()
            try:
                for batch in a.batches("stream", 0, t + seconds):
                    total += len(batch)
                    for path in batch:
                        if path in lookup:
                            q = lookup[path]
                            found.add(q["token"])
                            emitted.append(
                                request(f["run"], r, rd.addresses(r, path), rd.store)
                            )
            except TimeoutError:
                done = False
            if done:
                assert found == expected, (case, r, found ^ expected)
            records.append(
                dict(
                    run=f["run"],
                    rule=r,
                    goals=len(qs),
                    recognized=len(expected),
                    observed=len(found),
                    issued=total,
                    finished=done,
                )
            )
    for i, p in enumerate(emitted, 1):
        p["token"] = i
    res = check(d, binary(root), tape, emitted)
    hits = {w for _, _, w, _ in res["recall_verdicts"] if w is not None}
    return dict(
        case=case,
        first=[len(first), len(first & passing), len(first & hits)],
        high=[len(high), len(high & passing), len(high & hits)],
        runs=records,
        work=dict(counts),
    )


@torch.no_grad()
def bounded(root, case, arm):
    from stream_native import dynamic_wave

    base = Path(__file__).parent / "run-recall"
    d = folder(root, case)
    tape = read(d / "tape.json")
    high = set(
        read(base / "shared-composition" / (case + "-higher.json"))["negative_ids"]
    )
    first = {
        p["token"]
        for p in read(base / "oracle-headroom/divergence.json")[case]["missing"]
    }
    runs = {q["run"] for q in tape["requests"] if q["token"] in high | first}
    pol = get_policy(root, d, "free", "multi")
    probes = []
    with (d / "memory.jsonl").open() as f:
        for frame in map(json.loads, f):
            rows = pol.issue(frame) if arm == "fixed" else dynamic_wave(pol, frame)
            if frame["run"] in runs:
                for q in rows:
                    q["token"] = len(probes) + 1
                    probes.append(q)
    verified = check(d, binary(root), tape, probes)
    hits = {w for _, _, w, _ in verified["recall_verdicts"] if w is not None}
    return dict(
        case=case,
        arm=arm,
        first=len(first & hits),
        high=len(high & hits),
        paid=len(probes),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--bounded", action="store_true")
    a = ap.parse_args()
    torch.set_num_threads(1)
    out = []
    if a.bounded:
        out = [
            bounded(a.root.resolve(), c, arm)
            for arm in ("fixed", "dynamic")
            for c in ("fact", "loopfact", "sum-divisors")
        ]
        a.out.write_text(json.dumps(out, indent=2) + "\n")
        raise SystemExit(0)
    for c in ("fact", "loopfact", "sum-divisors"):
        v = audit(a.root.resolve(), c, a.seconds)
        out.append(v)
        print(c, v["first"], v["high"], flush=True)
        a.out.write_text(json.dumps(out, indent=2) + "\n")
