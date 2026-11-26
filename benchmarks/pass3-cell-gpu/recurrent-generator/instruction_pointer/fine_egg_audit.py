"""Offline minimal-change audit of frequent binding failures on independently reached EggCC states."""

import json
import subprocess
from collections import Counter

import torch

from cell_transaction import STATUS
from coverage_eval import choices
from discovery_native import configure
from discovery_sampling import encode
from discovery_score import packet
from discovery_states import cli
from discrete_cells import from_q
from draft_dispatch import Dispatch
from fine_credit import one_edit
from query_environment import online_memory
from recursive_train import folder
from transaction_native import execute


@torch.no_grad()
def audit(a):
    a.pages = 2
    a.generation_seed = 536
    d = folder(a.data, a.case)
    dest = a.out / "egg-audit" / a.case
    dest.mkdir(parents=True, exist_ok=True)
    failures = Counter()

    class Observer(Dispatch):
        def issue(self, items, txn, stats):
            replies = super().issue(items, txn, stats)
            for item in items:
                if STATUS[replies[item.uid][1]] == "binding":
                    failures[txn.run, item.cell] += 1
            return replies

    m = online_memory(a, d, dest, "D")
    marks, rates, _ = configure(
        a,
        m,
        "D",
        16,
        neural_setup=lambda cfg, mem, arm, n: choices(a, mem, "initial", n, 9633),
    )
    try:
        v = execute(
            a.data,
            a.case,
            study=Observer(m, marks, {"flow": rates}, "empty", 1, 536, 2, mode="page"),
            series=str(dest),
            seconds=300,
            observer_path=m.observer_path,
            runtime_binary=a.runtime_binary,
        )
    finally:
        m.close_observer()
    if sum(failures.values()) != v["verdicts"].get("binding", 0):
        raise ValueError("missed a native verdict")
    formal = (
        a.out / "native/9633/536/native-address" / a.case / "initial-k16-p2-b0/run.json"
    )
    baseline = json.loads(formal.read_bytes())
    if (v["state_sha"], v["verdicts"]) != (baseline["state_sha"], baseline["verdicts"]):
        raise ValueError("observation altered trajectory")
    tape = json.loads((dest / (a.case + "-stream-multi") / "issued.json").read_bytes())
    path = dest / "fork.json"

    def replay(rows, r, *flags):
        path.write_text(
            json.dumps(
                tape
                | {
                    "requests": rows,
                    "repair_events": [
                        e for e in tape["repair_events"] if e["run"] <= r
                    ],
                }
            )
        )
        return json.loads(
            subprocess.check_output(
                [
                    a.runtime_binary,
                    "replay",
                    d / "program.json",
                    path,
                    "audit",
                    str(r),
                    *flags,
                ]
            )
        )

    grouped = Counter()
    for (run, c), n in failures.items():
        grouped[run, c.rule] += n
    # Reserve audit capacity for 575 if it actually failed; the remaining slots
    # are filled by frequency. All selection and exact search follow termination.
    selected = sorted(grouped, key=lambda k: (k[1] != 575, -grouped[k], k))[:4]
    samples = []
    for run, rid in selected:
        prefix = [q for q in tape["requests"] if q["run"] < run]
        targets = [
            from_q(q)
            for q in replay(prefix, run - 1, "--audit-next-proofs")
            if q["rule"] == rid
        ]
        bad = sorted(
            (c for r, c in failures if r == run and c.rule == rid),
            key=lambda c: (-failures[run, c], c.refs),
        )
        rec = {
            "run": run,
            "rule": rid,
            "failures": grouped[run, rid],
            "unique_failed": len(bad),
            "native_options": len(targets),
            "verified": [],
        }
        base = replay(prefix, run, "--ept-origins")
        uid = max((q["token"] for q in prefix), default=0) + 1
        for wrong, right, j in one_edit(bad, targets):
            left = replay(prefix + [packet(wrong, run, uid)], run, "--ept-origins")
            alt = replay(prefix + [packet(right, run, uid)], run, "--ept-origins")
            g = dict(alt["ept"]["origins"]).get(uid, 0)
            if (
                left["counts"]["rejected"].get("binding", 0)
                == base["counts"]["rejected"].get("binding", 0) + 1
                and g
            ):
                rec["verified"].append(
                    {
                        "wrong": encode(wrong),
                        "replacement": encode(right),
                        "slot": j,
                        "gain": g,
                    }
                )
                if len(rec["verified"]) == 4:
                    break
        samples.append(rec)
    (a.out / "egg-audit.json").write_text(
        json.dumps(
            {
                "case": a.case,
                "policy": "initial",
                "seed": 536,
                "graph": v["state_sha"],
                "paid": v["paid"],
                "binding": sum(failures.values()),
                "rule575": sum(n for (r, c), n in failures.items() if c.rule == 575),
                "requests_by_rule": sorted(
                    Counter(
                        {
                            rid: sum(n for (_, r), n in grouped.items() if r == rid)
                            for _, rid in grouped
                        }
                    ).items()
                ),
                "samples": samples,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    p = cli()
    p.add_argument("--case", default="sum-divisors")
    torch.set_num_threads(1)
    audit(p.parse_args())
