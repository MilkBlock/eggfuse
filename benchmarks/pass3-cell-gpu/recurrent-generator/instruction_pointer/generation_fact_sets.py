"""Compare the identities of covered reference facts across operating points."""

import argparse
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from generation_frontier import CUTS
from generation_report import load_trials
from protocol_experiment import dump
from recursive_coverage import Target, snapshot
from recursive_train import folder, read


def compare(root, measured, case):
    d = folder(root, case)
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        ref = snapshot(root, d, "reference", "-", None, path)[0]
        target = Target(read(d / "program.json"), ref)
        seed = target.match(snapshot(root, d, "reference", "-", 0, path)[0])
    groups = {}
    for arm in ("A", "B", "residual", "fixed", "trained"):
        results = {}
        for cut in (0,) if arm == "fixed" else CUTS:
            w = (
                root
                / "generation-frontier"
                / f"{arm}-{cut:g}"
                / (case + "-stream-multi")
            )
            found = target.match(read(w / "state.json")) - seed
            endpoint = measured[case, arm, cut][0]
            assert (
                read(w / "metrics.json")["state_sha"] == endpoint["state_sha"]
                and len(found) == endpoint["coverage"]
            )
            results[cut] = found
        groups[arm] = results

    def delta(left, right):
        return dict(
            shared=len(left & right),
            gained=len(right - left),
            lost=len(left - right),
            gained_by_table=dict(Counter(target.gold[i][0] for i in right - left)),
            lost_by_table=dict(Counter(target.gold[i][0] for i in left - right)),
        )

    unions = {arm: set.union(*g.values()) for arm, g in groups.items()}
    return dict(
        zero=delta(groups["A"][0], groups["trained"][0]),
        against_any_A=delta(unions["A"], unions["trained"]),
        against_any_baseline=delta(
            set.union(*(unions[a] for a in ("A", "B", "residual", "fixed"))),
            unions["trained"],
        ),
        counts={
            arm: {str(c): len(v) for c, v in g.items()} for arm, g in groups.items()
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    args = p.parse_args()
    measured = load_trials(args.out)
    dump(
        args.out / "fact-identity.json",
        {c: compare(args.root, measured, c) for c in ("fact", "sum-divisors")},
    )
