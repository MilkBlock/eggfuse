"""Audit endpoint labels on the exact nested million-plan selection and actual failed trajectory."""

import json
import subprocess
from collections import Counter, defaultdict

import numpy as np

from continuation_audit import arguments
from data_scale_train import subset_indices
from recursive_train import binary, folder, read


def endpoint_audit(a):
    meta = read(a.previous / "corpus.json")
    sizes = [d["plans"] for d in meta]
    ids = subset_indices(sizes, sum(sizes), 1_000_000)
    selected = np.zeros(sum(sizes), bool)
    selected[ids] = True
    seen = Counter()
    mass = Counter()
    offset = 0
    for z in meta:
        d = a.previous / "programs" / f"{z['id']:04d}"
        p = np.load(d / "plans.npy")
        # Every original credited identity has a length-one window. Reconstruct
        # the exact teacher and counterfactual endpoint sequences by named binding.
        tape = read(d / "teacher.json")["requests"]
        cf = read(d / "counter.json")["requests"]
        credited = set(p[p[:, 2] == -1, 1].tolist())
        seq = defaultdict(list)
        for i, q in enumerate(tape):
            if i in credited:
                seq[q["run"]].append(i)
        last = max(seq)

        def key(q):
            return q["rule"], tuple(
                (r["address"]["token"], r["address"]["op"], r["version"])
                for r in q["parents"]
            )

        keys = {key(tape[i]): i for i in seq[last]}
        assert len(keys) == len(seq[last])
        paths = [*seq.values(), [keys[key(q)] for q in cf if q["run"] == last]]
        endings = set()
        for path in paths:
            for w in range(1, min(len(path), 4) + 1):
                endings.add(tuple(path[-w:]))
        for row in p[selected[offset : offset + len(p)], 1:]:
            window = tuple(row[row >= 0])
            w = len(window)
            kind = (
                "ends_a_witnessed_run"
                if window in endings
                else "ends_before_all_witnessed_run_ends"
            )
            seen[kind] += 1
            # Old sampler takes start=0 half the time, otherwise uniform [0,w).
            prob = 0.5 / (1 + w) + 0.5 * sum(1 / (1 + w - j) for j in range(w)) / w
            mass[kind] += prob
        offset += len(p)
    own = {}
    issued = a.out / "audit/s243-w2/sum-divisors-stream-multi/issued.json"
    d = folder(a.data, "sum-divisors")
    for stop in [1, 2, 3, 4, 8, 16, 64, 128, 207]:
        rows = json.loads(
            subprocess.check_output(
                [
                    binary(a.data),
                    "replay",
                    d / "program.json",
                    issued,
                    "time",
                    str(stop),
                    "--audit-next-proofs",
                ]
            )
        )
        own[stop + 1] = {
            "count": len(rows),
            "rules": Counter(q["rule"] for q in rows),
            "first": rows[:1],
        }
    (a.out / "endpoints.json").write_text(
        json.dumps({"counts": seen, "expected_zero_draws": mass, "next_native": own})
        + "\n"
    )


if __name__ == "__main__":
    endpoint_audit(arguments().parse_args())
