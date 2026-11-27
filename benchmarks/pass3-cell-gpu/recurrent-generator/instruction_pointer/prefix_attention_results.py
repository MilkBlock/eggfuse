"""Export per-intervention and free native records without counting repeated timings as trials."""

import csv
import hashlib
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean


def emit_csv(path, rows):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def export(d, out):
    out.mkdir(parents=True, exist_ok=True)
    cases = ("fact", "loopfact", "sum-divisors")
    audit = []
    swaps = []
    grad = []
    cohorts = {}
    training = {}
    live = []
    facts = {}
    files = []

    def read(name):
        p = d / name
        files.append(p)
        return json.loads(p.read_text())

    signatures = {}
    for case in cases:
        files.append(d / f"{case}.pkl")
        data = pickle.loads(files[-1].read_bytes())
        signatures[case] = {
            hashlib.sha256(pickle.dumps(s)).hexdigest() for s, _, _, _ in data
        }
        cohorts[case] = {
            "windows": len(data),
            "states": len(signatures[case]),
            "positive_targets": sum(len(t) for _, _, t, _ in data),
        }
        rows = read(f"audit-{case}.json")
        audit += rows
        prev = d.parent / "variable-completion" / f"binding-{case}.json"
        prior = {
            (r["run"], r["rule"], r["arm"]): r for r in json.loads(prev.read_text())
        }
        for r in rows:
            assert r["paid"] == sum(
                r[k]
                for k in ("binding", "guard", "other_rejects", "duplicates", "accepted")
            )
            if not r["forced"] and not r["seed"] and r["arm"] in ("base", "sparse"):
                old = prior[
                    r["run"], r["rid"], "KV" if r["arm"] == "base" else "sparse"
                ]
                assert all(
                    old[k] == r[k]
                    for k in (
                        "ops",
                        "productive",
                        "accepted",
                        "duplicates",
                        "binding",
                        "guard",
                    )
                )
        p = read(f"probe-results-{case}.json")
        swaps += p["swaps"]
        grad += p["gradients"]
        for arm in ("base", "rel"):
            for seed in (71, 113):
                tag = f"{case}-{arm}-{seed}"
                training[tag] = read(tag + ".json")
                files.append(d / (tag + ".pt"))
        for budget in ("live", "paid"):
            for p in sorted(d.glob(f"{budget}-{case}-*.json")):
                x = read(p.name)
                stats = x["stats"]
                reject = x["receipts"]["rejected"]
                row = {
                    k: x[k]
                    for k in (
                        "case",
                        "arm",
                        "seed",
                        "unique",
                        "rep",
                        "covered",
                        "reference",
                        "coverage",
                        "ops",
                        "ept",
                        "eps",
                        "wall",
                        "generate_s",
                        "publication_s",
                        "prepare_s",
                        "graph",
                    )
                }
                live.append(
                    dict(
                        **row,
                        budget=budget,
                        paid=stats["paid"],
                        signed=stats["neural_tokens"],
                        opportunities=x["count"]["opportunities"],
                        untriggered=reject.get("untriggered_rule", 0),
                        binding=reject.get("binding", 0),
                        duplicate=x["receipts"]["duplicates"],
                        guard=reject.get("guard", 0),
                    )
                )
                facts[x["graph"]] = x["facts"]
                if budget == "paid":
                    assert stats["paid"] == 96
    expected_rows = {"live": 26, "paid": 10}
    for case in cases:
        for budget, expected in expected_rows.items():
            trials = [x for x in live if x["case"] == case and x["budget"] == budget]
            assert len(trials) == expected, (case, budget, len(trials))
        for arm, suffix in (("base", "KV"), ("sparse", "sparse-paired")):
            current = read(f"live-{case}-{arm}-0-0-0.json")
            previous = json.loads(
                (
                    d.parent
                    / "variable-completion"
                    / f"free-binding-{case}-full-0-{suffix}.json"
                ).read_text()
            )
            assert all(
                current[k] == previous[k] for k in ("stats", "ops", "facts", "graph")
            )
    groups = defaultdict(list)
    for row in audit:
        groups[
            tuple(row[k] for k in ("arm", "seed", "arity", "forced", "index"))
        ].append(row)
    summary = []
    for (arm, seed, arity, forced, idx), rs in sorted(groups.items()):
        witnesses = [t for r in rs for t in r["probabilities"]]
        summary.append(
            dict(
                arm=arm,
                seed=seed,
                arity=arity,
                given_first=forced,
                old_index=idx,
                windows=len(rs),
                **{
                    k: sum(r[k] for r in rs)
                    for k in (
                        "paid",
                        "binding",
                        "duplicates",
                        "accepted",
                        "productive",
                        "ops",
                    )
                },
                window_new_facts=sum(len(r["new_facts"]) for r in rs),
                window_lost_facts=sum(len(r["lost_facts"]) for r in rs),
                witnesses=len(witnesses),
                full_token_probability=mean(t["p_token"] for t in witnesses),
                **{
                    f"parent{j + 1}": mean(t["fields"][j] for t in witnesses)
                    if j < arity
                    else ""
                    for j in range(3)
                },
            )
        )
    for case in cases:
        cohorts[case]["matching_snapshot_hashes_in_other_programs"] = len(
            signatures[case] & set.union(*(signatures[c] for c in cases if c != case))
        )
    emit_csv(out / "summary.csv", summary)
    emit_csv(out / "native.csv", live)
    emit_csv(
        out / "gradients.csv",
        [
            {k: v for k, v in g.items() if k != "norms"}
            | dict(
                zip(
                    ("query", "key", "source_value", "candidate_value"),
                    g["norms"],
                    strict=True,
                )
            )
            for g in grad
        ],
    )
    for name, obj in [
        ("training", training),
        ("cohorts", cohorts),
        ("facts", facts),
        ("field-swaps", swaps),
    ]:
        (out / (name + ".json")).write_text(json.dumps(obj, separators=(",", ":")))
    (out / "interventions.jsonl").write_text(
        "".join(json.dumps(x, separators=(",", ":")) + "\n" for x in audit)
    )
    (out / "manifest.json").write_text(
        json.dumps(
            {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},
            indent=2,
        )
    )


if __name__ == "__main__":
    export(Path(sys.argv[1]), Path(sys.argv[2]))
