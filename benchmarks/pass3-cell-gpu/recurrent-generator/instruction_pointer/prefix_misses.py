"""Offline earliest omitted binding and its downstream counterfactual on a local-prefix tape."""

import argparse, json, subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import torch
from generation_frontier import Generator
from higher_replacement import send
from live_reach_funnel import Watch, key
from protocol_experiment import dump
from reachability_rollout import ReachStream
from recursive_train import binary, folder, read
from recursive_coverage import Target, snapshot
from train_reachability import Prefix
from transaction_native import execute

OLD = Path("run-recall/structural-reach")


class WitnessWatch(Watch, ReachStream):
    pass


class Inject(Generator):
    def run_snapshot(self, f, pub, rd, model, txn, stats, deadline):
        super().run_snapshot(f, pub, rd, model, txn, stats, deadline)
        for q in self.inject.get(f["run"], ()):
            refs = np.array(
                [
                    [p["address"]["token"], p["address"]["op"], p["version"]]
                    for p in q["parents"]
                ],
                dtype=np.int64,
            ).reshape(1, -1, 3)
            if send(txn, q["rule"], refs)[0, 1] != 0:
                raise ValueError("counterfactual witness failed")


def run(root, out, case, second=False):
    d = folder(root, case)
    work = root / "structural-reach/learned-nolook" / (case + "-stream-multi")
    prior = {}
    if second:
        first = read(out / f"miss-{case}.json")
        prior[first["run"]] = first["earliest"]
        work = root / "prefix-omission" / (case + "-stream-multi")
    tape = read(work / "issued.json")
    args = [binary(root), "replay", d / "program.json", work / "issued.json", "time"]
    with TemporaryDirectory() as t:
        p = Path(t) / "file.json"
        goal = Target(
            read(d / "program.json"), snapshot(root, d, "reference", "-", None, p)[0]
        )
        have = goal.match(read(work / "state.json"))
        missing = sorted(set(range(len(goal.gold))) - have)
        miss = []
        for r in range(1, read(work / "metrics.json")["runs"] + 1):
            qs = json.loads(
                subprocess.check_output([*args, str(r - 1), "--audit-next-proofs"])
            )
            if qs:
                dump(p, {**tape, "requests": qs})
                checks = json.loads(
                    subprocess.check_output([*args, str(r), "--recall", p])
                )["recall_verdicts"]
                lookup = {q["token"]: q for q in qs}
                miss = [
                    lookup[i]
                    for _, i, owner, why in checks
                    if owner is None and why == "off_reference"
                ]
                if miss:
                    break
        if not miss:
            raise ValueError("no reachable omission")
        g = Inject(root, "A", 0, case)
        g.inject = {**prior, r: miss}
        g.targets = {
            (r, rid): [q for q in miss if q["rule"] == rid]
            for rid in {q["rule"] for q in miss}
        }
        g.outcome = {}
        g.stream_type = WitnessWatch
        g.dense = g.prefix_open = g.terminal_open = g.relaxed = False
        g.no_look = True
        g.adapter = Prefix().eval()
        g.adapter.load_state_dict(torch.load(OLD / "prefix.pt", weights_only=True))
        m = execute(
            root,
            case,
            study=g,
            series="prefix-omission-2" if second else "prefix-omission",
            seconds=200,
        )
        end = goal.match(
            read(
                root
                / ("prefix-omission-2" if second else "prefix-omission")
                / (case + "-stream-multi")
                / "state.json"
            )
        )
        dump(
            out / f"miss-{case}{'-second' if second else ''}.json",
            dict(
                run=r,
                earliest=[
                    dict(
                        rule=q["rule"],
                        parents=q["parents"],
                        stage=g.outcome.get(key(q)),
                    )
                    for q in miss
                ],
                missing=len(missing),
                fact_detail=[
                    dict(
                        row=i,
                        table=goal.gold[i][0],
                        values=goal.gold[i][1],
                        recovered=i in end,
                    )
                    for i in missing
                ]
                if case == "fact"
                else [],
                recovered=len(end - have),
                lost=len(have - end),
                termination=m["termination"],
                exact_endpoint=m["exact_endpoint"],
            ),
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("cases", nargs="+")
    p.add_argument("--second", action="store_true")
    a = p.parse_args()
    torch.set_num_threads(1)
    for c in a.cases:
        run(a.root, a.out, c, a.second)
