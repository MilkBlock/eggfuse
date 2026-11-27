"""Export paired results and learning curves without pooling independent runs as trials."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from statistics import mean, median

from discovery_score import write_csv
from metal_scaling import CASES
from next_cell_corpus import digest

ARMS = ["factored", "initial", "ce24", "ce200", "ce200mixed"]
SEEDS = [9633, 5003]


def read(p):
    return json.loads(p.read_bytes())


def runs(a):
    rows = []
    facts = {}
    for path in sorted((a.out / "native").glob("*/*/native-address/*/*/run.json")):
        x = read(path)
        seed = int(path.relative_to(a.out / "native").parts[0])
        w = x["work"]
        rows.append(
            dict(
                case=x["case"],
                arm=x["method"],
                seed=seed,
                block=x["block"],
                facts=x["covered"],
                reference=x["reference"],
                ops=x["signed_ops"],
                paid=x["paid"],
                slots=x["device"].get("neural_slot_attempts", 0),
                issued=w.get("final_tokens", 0),
                ept=x["ept"],
                eps=x["cold_eps"],
                seconds=x["cold_wall"],
                state_sha=x["state_sha"],
                stop=x["termination"],
                accepted=x["verdicts"].get("accepted", 0),
                sampling_seconds=w["sampling_seconds"],
                retired_or_invalid_suffix=w.get("stale_released", 0),
                instantiated=w.get("instantiated", 0),
                higher_completed=w.get("higher_completed", 0),
                suffix=w.get("lowered_suffix", 0),
            )
        )
        key = f"{seed}/{x['case']}/{x['method']}"
        if key in facts and facts[key] != x["facts"]:
            raise ValueError("different fact identities in timing repetitions")
        facts[key] = x["facts"]
    summary = []
    for case in CASES:
        for arm in ARMS:
            by_seed = []
            for seed in SEEDS:
                selected = [
                    r
                    for r in rows
                    if (r["case"], r["arm"], r["seed"]) == (case, arm, seed)
                ]
                if len(selected) != (2 if seed == 9633 else 1):
                    raise ValueError(f"incomplete native run {case}/{arm}/{seed}")
                if len({(r["state_sha"], r["ops"], r["paid"]) for r in selected}) != 1:
                    raise ValueError("non-reproducible paid operations or final graph")
                r = selected[0]
                by_seed.append(
                    dict(
                        coverage=100 * r["facts"] / r["reference"],
                        ept=r["ept"],
                        eps=median(v["eps"] for v in selected),
                        slots=r["slots"],
                        paid=r["paid"],
                    )
                )
            summary.append(
                dict(
                    case=case,
                    arm=arm,
                    **{k: mean(v[k] for v in by_seed) for k in by_seed[0]},
                )
            )
    write_csv(a.dest / "native.csv", rows)
    write_csv(a.dest / "formal.csv", summary)
    (a.dest / "facts.json").write_text(json.dumps(facts, separators=(",", ":")) + "\n")


def paired(a):
    sums = defaultdict(lambda: defaultdict(float))
    detail = []
    for seed in SEEDS:
        for case in CASES:
            for source in ("teacher", "rollout"):
                directory = a.out / f"paired-{seed}" / source / case
                files = sorted(p for p in directory.glob("*.json") if p.stem.isdigit())
                candidates = sorted(
                    s["run"] for s in read(a.archive / source / case / "states.json")
                )
                expected = {
                    candidates[i]
                    for i in np.linspace(
                        0, len(candidates) - 1, min(4, len(candidates)), dtype=int
                    )
                }
                if {int(p.stem) for p in files} != expected:
                    raise ValueError(f"incomplete frozen runs: {directory}")
                for path in files:
                    xs = read(path)
                    if len(xs) != len(ARMS) * 2 * 6:
                        raise ValueError("missing frozen arm or draw")
                    for x in xs:
                        k = (case, source, x["arm"], x["kind"], x["budget"])
                        row = sums[k]
                        for f in (
                            "slots",
                            "completed",
                            "proposed",
                            "distinct",
                            "hit",
                            "reference_owners",
                            "seconds",
                            "censored",
                        ):
                            row[f] += x[f]
                        if "native" in x:
                            row["accepted"] += x["native"].get("accepted", 0)
                            row["productive"] += x["positive_requests"]
                        row["draws"] += 1
                        detail.append(
                            dict(
                                case=case,
                                source=source,
                                seed=seed,
                                run=int(path.stem),
                                **{k: v for k, v in x.items() if k != "native"},
                                receipts=json.dumps(x.get("native")),
                            )
                        )
    write_csv(
        a.dest / "free-generation.csv",
        [
            dict(case=k[0], source=k[1], arm=k[2], kind=k[3], budget=k[4], **v)
            for k, v in sums.items()
        ],
    )
    write_csv(a.out / "frozen-detail.csv", detail)


def main(a):
    a.dest.mkdir(exist_ok=True, parents=True)
    runs(a)
    paired(a)
    curves = []
    for p in sorted(a.out.glob("curve-*.json")):
        curves.extend(dict(arm=p.name.split("-")[1], **r) for r in read(p))
    write_csv(a.dest / "learning.csv", curves)
    higher = []
    for p in sorted((a.out / "unseen").glob("*/native-address/*/*/run.json")):
        x = read(p)
        w = x["work"]
        trace = read(a.out / "unseen-trace" / p.relative_to(a.out / "unseen"))
        if any(
            trace[k] != x[k]
            for k in ("paid", "facts", "signed_ops", "state_sha", "verdicts")
        ):
            raise ValueError("instrumenting Higher selection changed native semantics")
        higher.append(
            dict(
                case=x["case"],
                seed=p.relative_to(a.out / "unseen").parts[0],
                arm=x["method"],
                covered=x["covered"],
                reference=x["reference"],
                slots=x["device"]["neural_slot_attempts"],
                issued=w["final_tokens"],
                higher_draws=trace["device"].get("higher_template_draws", 0),
                higher_bound=trace["device"].get("higher_fully_bound", 0),
                higher_issued=trace["device"].get("higher_returned", 0),
                instantiated=w.get("instantiated", 0),
                completed=w.get("higher_completed", 0),
                suffix=w.get("lowered_suffix", 0),
                ops=x["signed_ops"],
                paid=x["paid"],
                ept=x["ept"],
                eps=x["cold_eps"],
            )
        )
    if len(higher) != 12:
        raise ValueError("missing unseen-layout controls")
    write_csv(a.dest / "unseen.csv", higher)
    write_csv(
        a.dest / "weights.csv",
        [
            dict(
                path=str(p.relative_to(a.out)),
                sha256=digest(p.read_bytes()),
                bytes=p.stat().st_size,
            )
            for p in sorted((a.out / "weights").glob("*/*.pt"))
        ],
    )
    for src in [
        "inventory.json",
        "corpus-ce200mixed.json",
        "corpus-ce24.json",
        "transfer-nll.csv",
        "family-free.csv",
    ]:
        (a.dest / src).write_bytes((a.out / src).read_bytes())
    audit = read(a.out / "first-request-audit.json")
    (a.dest / "first-request-audit.json").write_text(
        json.dumps(
            dict(
                samples=len(audit),
                accepted=sum(r["accepted"] for r in audit),
                positive_origin=sum(r["signed_origin"] > 0 for r in audit),
                positive_margin=sum(r["ops_delta"] > 0 for r in audit),
                sha256=digest((a.out / "first-request-audit.json").read_bytes()),
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--dest", required=True, type=Path)
    main(p.parse_args())
