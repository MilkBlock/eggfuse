"""Diagnostic only: fork the learner's own signed prefix to get the exact next Run.

In the fully open intervention all canonical valid tuples can be named. This
witness-driven control avoids materializing rejected Cartesian products. Its
ordering and time are native-oracle properties, never neural execution credit.
"""

import argparse, json, subprocess
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import torch
from higher_replacement import send
from protocol_experiment import digest, dump
from recursive_train import folder, read
from recursive_coverage import Target, snapshot
from transaction_native import execute


class Fork:
    def __init__(self, exe, program, directory):
        self.exe = exe
        self.program = program
        self.path = directory / "prefix.json"
        self.ledger = dict(
            schema="cell-token-replay/v2",
            program_sha256=digest(program),
            requests=[],
            repair_events=[],
        )

    def run_snapshot(self, f, pub, rd, model, txn, stats, deadline):
        if not f["rules"]:
            return
        run = f["run"]
        self.path.write_text(json.dumps(self.ledger, separators=(",", ":")))
        rows = json.loads(
            subprocess.check_output(
                [
                    self.exe,
                    "replay",
                    self.program,
                    self.path,
                    "time",
                    str(run - 1),
                    "--audit-next-proofs",
                ]
            )
        )
        stats["exact_next_forks"] += 1
        by = defaultdict(list)
        for q in rows:
            assert q["run"] == run
            by[q["rule"]].append(q)
        for rule, qs in by.items():
            for i in range(0, len(qs), txn.capacity):
                part = qs[i : i + txn.capacity]
                k = len(part[0]["parents"])
                refs = np.array(
                    [
                        [
                            (p["address"]["token"], p["address"]["op"], p["version"])
                            for p in q["parents"]
                        ]
                        for q in part
                    ],
                    np.int64,
                ).reshape(len(part), k, 3)
                response = send(txn, rule, refs)
                if np.any(response[:, 1] != 0):
                    raise ValueError(
                        ("oracle proof rejected", run, rule, response[:, 1].tolist())
                    )
                for q, token in zip(part, response[:, 0]):
                    q["token"] = int(token)
                    self.ledger["requests"].append(q)


def audit(root, out, exe, case):
    d = folder(root, case)
    series = "structural-oracle"
    with TemporaryDirectory() as t:
        policy = Fork(exe, d / "program.json", Path(t))
        m = execute(root, case, study=policy, series=series, seconds=1500)
        ref, exact = snapshot(root, d, "reference", "-", None, Path(t) / "state")
        target = Target(read(d / "program.json"), ref)
        seed = target.match(
            snapshot(root, d, "reference", "-", 0, Path(t) / "state")[0]
        )
    work = root / series / (case + "-stream-multi")
    m.update(
        derived=len(target.match(read(work / "state.json")) - seed),
        den=len(target.gold) - len(seed),
        reference_sha=exact["state_sha"],
    )
    m.pop("trace")
    m.pop("guard_failures")
    dump(out / f"oracle-open-{case}.json", m)
    print(case, m["termination"], m["derived"], m["exact_endpoint"], flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("exe", type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    torch.set_num_threads(1)
    for c in a.cases:
        audit(a.root, a.out, a.exe, c)
