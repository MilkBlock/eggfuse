"""Audit named witnesses at fixed-policy Run entry after the independent evaluation."""

import argparse
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from control_credit_pairs import digest
from discovery_states import read, save
from dual_credit import marginal
from execution_control_data import effects
from recursive_train import folder


def audit(a, endpoint):
    stats = read(endpoint)
    case = stats["case"]
    program = folder(a.data, case) / "program.json"
    tape = read(endpoint.parent / (case + "-stream-multi") / "issued.json")
    trace = stats["trace"]
    # Stratify by the actual presence of an admission. No test target informs training.
    buckets = [[], []]
    last = dict(paid=0, accepted=0, elapsed=0)
    for row in trace:
        delta = {k: row[k] - last[k] for k in last}
        if delta["paid"] > 0:
            buckets[int(delta["accepted"] > 0)].append((row["run"], delta))
        last = {k: row[k] for k in last}
    selected = [
        seq[j]
        for seq in buckets
        if seq
        for j in sorted(
            {0, len(seq) // 4, len(seq) // 2, 3 * len(seq) // 4, len(seq) - 1}
        )
    ]
    results = []
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "tape.json"

        def replay(rows, run=None, exact=False):
            save(
                path,
                dict(
                    tape,
                    requests=rows,
                    repair_events=[
                        e
                        for e in tape["repair_events"]
                        if run is None or e["run"] <= run
                    ],
                ),
            )
            cmd = [a.runtime_binary, "replay", program, path, "audit"]
            if run is not None:
                cmd.append(str(run))
            cmd.append("--audit-next-proofs" if exact else "--ept-origins")
            report = json.loads(subprocess.check_output(cmd))
            if exact:
                return report
            return dict(
                sha=report["state_sha"],
                ops=effects(report),
                origins=dict(report["ept"]["origins"]),
            )

        allq = tape["requests"]
        if replay(allq)["sha"] != stats["state_sha"]:
            raise ValueError(
                "accepted native tape does not reproduce autonomous endpoint"
            )
        for r, delta in sorted(selected):
            prefix = [q for q in allq if q["run"] < r]
            actual = [q for q in allq if q["run"] == r]
            if len(actual) != delta["accepted"]:
                raise ValueError("window admission total differs from tape")
            exact = replay(prefix, r - 1, True)
            uid = max((q["token"] for q in prefix), default=0) + 1
            teacher = [
                dict(q, token=uid + i)
                for i, q in enumerate(sorted(exact, key=digest)[:128])
            ]
            base = replay(prefix, r)

            def gain(rows):
                return marginal(
                    base, replay(prefix + rows, r) if rows else base, prefix, rows
                )

            t = gain(teacher)
            n = gain(actual)
            results.append(
                dict(
                    run=r,
                    state=digest([tape["program_sha256"], r, prefix]),
                    policy=stats["method"],
                    policy_credits=n,
                    requests=actual,
                    paid=delta["paid"],
                    window_elapsed=delta["elapsed"],
                    exact_options=len(exact),
                    tried=len(teacher),
                    teacher_ops=None if t is None else sum(t),
                    teacher_witnesses=None
                    if t is None
                    else [[q, g] for q, g in zip(teacher, t, strict=True) if g],
                    realized_ops=None if n is None else sum(n),
                    control_preference=None,
                )
            )
    save(a.out / "egg-dual" / (case + ".json"), results)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("out", "data", "runtime-binary"):
        p.add_argument("--" + name, required=True, type=Path)
    a = p.parse_args()
    (a.out / "egg-dual").mkdir(exist_ok=True)
    for case in ("fact", "loopfact", "sum-divisors"):
        audit(
            a,
            a.out
            / "native/9633/536/native-address"
            / case
            / "dual-witness-k16-p2-b0/run.json",
        )
