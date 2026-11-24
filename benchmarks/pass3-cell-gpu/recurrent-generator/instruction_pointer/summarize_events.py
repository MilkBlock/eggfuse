"""Compare counterbalanced independent runs using the original CCP token ledger."""

import csv
import json
from pathlib import Path
from statistics import median

OUT = Path("run-recall/cell-events")
rows = []
for case in (
    "fact",
    "sum-divisors",
    "grammar-36719037",
    "grammar-benefit-held-deep-11901379",
):
    baseline = []
    for mode in ("local", "B", "C", "D"):
        ms = [
            json.loads((OUT / f"{case}_{mode}_{i}.json").read_bytes())
            for i in range(4, 8)
        ]
        m = ms[0]
        assert all(
            (q["state_sha"], q["facts"], q["paid"])
            == (m["state_sha"], m["facts"], m["paid"])
            for q in ms
        )
        if mode == "local":
            baseline = ms
        w = m["work"]
        rows.append(
            dict(
                case=case,
                arm=mode,
                facts=m["facts"],
                reference=m["reference"],
                same_graph=m["state_sha"] == baseline[0]["state_sha"],
                termination=m["termination"],
                paid=m["paid"],
                neural_tokens=m["neural_tokens"],
                ept=m["ept"],
                eps=median(q["eps"] for q in ms),
                wall=median(q["wall"] for q in ms),
                wins_vs_A=sum(q["wall"] < a["wall"] for q, a in zip(ms, baseline)),
                templates=w.get("generated_templates", 0),
                source_reads=w.get("source_port_reads", 0),
                candidate_visits=w.get("visits", 0),
                index_reads=w.get("index_port_reads", 0),
                posting_reads=w.get("posting_index_reads", 0),
                interface_reads=w.get("interface_reads", 0),
                complete_scores=w.get(
                    "complete_candidate_scores", w.get("tuple_scored", 0)
                ),
                accepted=m["verdicts"].get("accepted", 0),
                proofs=m["proof_paid"],
                acceptance=m["verdicts"].get("accepted", 0) / max(1, m["proof_paid"]),
                duplicate=m["verdicts"].get("duplicate", 0),
                missed=m["reference"] - m["facts"],
                old_wakes=w.get("old_port_wakes", 0),
                local_operands=w.get("local_result_operands", 0),
                response_queries=w.get("response_queries", 0),
            )
        )
with (OUT / "paired.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
for r in rows:
    print(
        r["case"],
        r["arm"],
        r["facts"],
        r["candidate_visits"],
        round(r["ept"], 4),
        round(r["eps"]),
        r["wins_vs_A"],
    )
