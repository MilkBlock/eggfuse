"""Teacher drives publications; neural proposals are checked offline against that same Run."""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import numpy as np
import torch
from generation_frontier import Generator, CUTS, CASES
from protocol_experiment import dump
from recursive_train import binary, folder, read
from transaction_native import execute


class ProbeSink:
    def __init__(self, txn, inverse):
        self.txn = txn
        self.inverse = inverse
        self.items = []

    def __getattr__(self, k):
        return getattr(self.txn, k)

    def proofs_from_paths(self, stream, paths):
        refs = [stream.port_refs(j)[paths[:, j]] for j in np.argsort(stream.order)]
        rows = torch.stack(refs, 1).tolist() if refs else [[] for _ in paths]
        for parents in rows:
            self.items.append(
                dict(
                    rule=stream.rule,
                    run=self.txn.run,
                    parents=[
                        dict(
                            address=dict(token=self.inverse.get(t, t), op=op), version=v
                        )
                        for t, op, v in parents
                    ],
                )
            )


class Frozen:
    def __init__(self, policy, tape, sampled=None):
        self.sampled = sampled
        self.policy = policy
        self.items = []
        self.by = defaultdict(list)
        self.forward = {}
        self.inverse = {}
        for q in tape["requests"]:
            self.by[q["run"]].append(q)

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        if self.sampled is None or txn.run in self.sampled:
            sink = ProbeSink(txn, self.inverse)
            self.policy.run_snapshot(frame, pub, rd, model, sink, stats, deadline)
            self.items.extend(sink.items)
        for start in range(0, len(self.by[txn.run]), txn.capacity):
            rows = self.by[txn.run][start : start + txn.capacity]
            op = np.zeros((len(rows), 5), dtype=np.int64)
            refs = []
            for i, q in enumerate(rows):
                for ref in q["parents"]:
                    a = ref["address"]
                    refs.append(
                        (
                            self.forward.get(a["token"], a["token"]),
                            a["op"],
                            ref["version"],
                            -1,
                        )
                    )
                op[i, 2:] = (q["rule"], -1, len(refs))
                new = txn.paid + 1 + i
                self.forward[q["token"]] = new
                self.inverse[new] = q["token"]
            r = txn.submit(op, np.array(refs, dtype=np.int64).reshape(-1, 4))
            if not torch.all(r[:, 1] == 0):
                raise ValueError(("teacher rejected", txn.run, r[:, 1]))


def check(root, out, case, arm, cut, limit=24, stratified=False):
    from generation_targets import TrainedGenerator

    d = folder(root, case)
    tape = read(d / "tape.json")
    policy = (
        TrainedGenerator(root, out, arm, cut, case)
        if arm in ("trained", "unranked")
        else Generator(root, arm, cut, case)
    )
    sampled = None
    if stratified:
        if arm not in ("A", "trained", "unranked"):
            raise ValueError("sparse evaluation supports stateless decision heads only")
        productive = sorted({q["run"] for q in tape["requests"]})
        sampled = {
            productive[j]
            for j in np.linspace(
                0, len(productive) - 1, min(24, len(productive)), dtype=int
            )
        }
        limit = read(d / "capture.json")["runs"]
    st = Frozen(policy, tape, sampled)
    m = execute(
        root, case, study=st, limit=limit, series="generation-shadow", seconds=240
    )
    with TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probe.json"
        ids = {
            q["token"]
            for q in tape["requests"]
            if q["run"] <= m["runs"] and (sampled is None or q["run"] in sampled)
        }
        exact = {
            (
                q["run"],
                q["rule"],
                tuple(
                    (a["address"]["token"], a["address"]["op"], a["version"])
                    for a in q["parents"]
                ),
            )
            for q in tape["requests"]
            if q["token"] in ids
        }
        literal = 0
        for i, q in enumerate(st.items, 1):
            q["token"] = i
            literal += int(
                (
                    q["run"],
                    q["rule"],
                    tuple(
                        (a["address"]["token"], a["address"]["op"], a["version"])
                        for a in q["parents"]
                    ),
                )
                in exact
            )
        dump(probe, {**tape, "requests": st.items})
        report = json.loads(
            subprocess.check_output(
                [
                    binary(root),
                    "replay",
                    d / "program.json",
                    d / "tape.json",
                    "time",
                    str(limit),
                    "--recall",
                    probe,
                ]
            )
        )
        assert report["state_sha"] == m["state_sha"] and len(
            report["recall_verdicts"]
        ) == len(st.items)
        by = defaultdict(set)
        for run, _, owner, _ in report["recall_verdicts"]:
            if owner in ids:
                by[run].add(owner)
        expected = defaultdict(set)
        for q in tape["requests"]:
            if q["token"] in ids:
                expected[q["run"]].add(q["token"])
        useful = {p["address"]["token"] for q in tape["requests"] for p in q["parents"]}
        ordered = defaultdict(list)
        for run, probe_id, owner, _ in report["recall_verdicts"]:
            ordered[run].append((probe_id, owner))
        early = {}
        for percent in (1, 10, 50, 100):
            probes = hits = future = 0
            for run, observed in ordered.items():
                n = (len(observed) * percent + 99) // 100
                owners = {owner for _, owner in sorted(observed)[:n]} & expected.get(
                    run, set()
                )
                probes += n
                hits += len(owners)
                future += len(owners & useful)
            early[percent] = dict(
                probes=probes, distinct_teacher=hits, later_consumed=future
            )
        return dict(
            runs=m["runs"],
            reference=len(ids),
            matched=sum(len(by[k] & v) for k, v in expected.items()),
            first_fraction_per_run=early,
            literal_proposals=literal,
            proposed=len(st.items),
            by_run={k: [len(by[k] & v), len(v)] for k, v in expected.items()},
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--arms", nargs="+", default=["A", "B", "residual", "fixed"])
    p.add_argument("--cases", nargs="+", default=CASES)
    p.add_argument("--cuts", type=float, nargs="+", default=CUTS)
    p.add_argument("--stratified", action="store_true")
    a = p.parse_args()
    torch.set_num_threads(1)
    for arm in a.arms:
        path = a.out / (("stratified-" if a.stratified else "shadow-") + arm + ".json")
        results = read(path) if path.exists() else {}
        for c in a.cases:
            results.setdefault(c, {}).update(
                {
                    str(t): check(a.root, a.out, c, arm, t, stratified=a.stratified)
                    for t in a.cuts
                    if arm != "fixed" or t == 0
                }
            )
            dump(path, results)
            print(arm, c, flush=True)
