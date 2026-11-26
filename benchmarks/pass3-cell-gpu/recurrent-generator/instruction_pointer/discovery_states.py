"""Build offline named one-Run forks from both teacher and independently issued tapes."""

import json
import os
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from discrete_reference import Reference
from generation_shadow import ProbeSink
from metal_scaling import CASES
from query_witnesses import arguments
from recursive_rollout import get_policy
from recursive_train import folder, read


def cli():
    p = arguments()
    p.add_argument("--contract", type=Path, required=True)
    p.add_argument("--cases", nargs="+", default=CASES)
    return p


def save(path, obj):
    path.write_text(json.dumps(obj, separators=(",", ":")) + "\n")


def replay(a, case, tape, *args, env=None):
    return json.loads(
        subprocess.check_output(
            [
                a.runtime_binary,
                "replay",
                folder(a.data, case) / "program.json",
                tape,
                "audit",
                *map(str, args),
            ],
            env=env,
        )
    )


def issued(a, case):
    directory = a.contract / "native-address" / case / "D-k16-p2-b0"
    return directory / (case + "-stream-multi") / "issued.json", read(
        directory / "run.json"
    )


def prepare(a, case):
    for source in ("teacher", "rollout"):
        dest = a.out / source / case
        dest.mkdir(exist_ok=True, parents=True)
        if (dest / "states.json").exists():
            continue
        program = folder(a.data, case)
        stalls = {}
        if source == "teacher":
            tape = program / "tape.json"
            runs = sorted(
                int(f.name.split("-teacher-")[1].split(".")[0])
                for f in (a.contract / "eval/old").glob(case + "-teacher-*.pkl.gz")
            )
        else:
            tape, original = issued(a, case)
        env = dict(os.environ, EGGFUSE_QUERY_OBSERVER=str(dest / "scheduler.jsonl"))
        report = replay(
            a, case, tape, "--memory", dest / "frames.jsonl", "--ept-origins", env=env
        )
        rows = read(tape)
        gains = dict(report["ept"]["origins"])
        assert report["counts"]["accepted"] == len(rows["requests"])
        by = defaultdict(list)
        for q in rows["requests"]:
            by[q["run"]].append(q)
        if source == "rollout":
            assert report["state_sha"] == original["state_sha"]
            total = original["runs"]
            active = [
                r
                for r in range(1, total + 1)
                if any(gains.get(q["token"], 0) > 0 for q in by[r])
            ]
            start = active[0] + 1 if active else 1
            first = next((r for r in range(start, total + 1) if r not in active), None)
            last = active[-1] + 1 if active else 1
            stalls = {
                k: r
                for k, r in [("first_gap", first), ("terminal_tail", last)]
                if r is not None and r <= total
            }
            rng = np.random.default_rng(673)
            strata = [active, [r for r in range(1, total + 1) if r not in active]]
            runs = sorted(
                set(stalls.values()).union(
                    *(
                        map(int, rng.choice(xs, min(12, len(xs)), replace=False))
                        for xs in strata
                    )
                )
            )
        stream = Reference(original_order=True)
        policy = get_policy(a.data, program, "free", "multi")
        summaries = []
        for line in (dest / "frames.jsonl").open():
            frame = json.loads(line)
            r = frame["run"]
            if stalls:
                policy.reader.advance(frame)
            if r not in runs:
                continue
            unit = dest / str(r)
            unit.mkdir(exist_ok=True)
            prefix = [q for q in rows["requests"] if q["run"] < r]
            if source == "teacher":
                fork = by[r]
            else:
                fork = replay(a, case, tape, r - 1, "--audit-next-proofs")
            assert all(q["run"] == r for q in fork)
            path = unit / "oracle.json"
            save(path, dict(rows, requests=prefix + fork))
            audit = replay(a, case, path, r, "--ept-origins")
            assert audit["counts"]["accepted"] == len(prefix) + len(fork)
            value = dict(audit["ept"]["origins"])
            save(unit / "gold.json", [[q, value.get(q["token"], 0)] for q in fork])
            item = dict(
                run=r,
                available=len(fork),
                productive=sum(value.get(q["token"], 0) > 0 for q in fork),
                original_effective=sum(gains.get(q["token"], 0) for q in by[r]),
                stall=[k for k, v in stalls.items() if v == r],
            )
            if r in stalls.values():
                sink = ProbeSink(SimpleNamespace(run=r), {})
                stream.run_snapshot(
                    frame,
                    None,
                    policy.reader,
                    policy.model,
                    sink,
                    Counter(),
                    float("inf"),
                )
                uid = max((q["token"] for q in prefix), default=0) + 1
                requests = [dict(q, token=uid + i) for i, q in enumerate(sink.items)]
                probe = unit / "stream.json"
                save(probe, dict(rows, requests=prefix + requests))
                actual = replay(a, case, probe, r, "--ept-origins")
                ops = dict(actual["ept"]["origins"])
                item.update(
                    stream_paid=len(requests),
                    stream_accepted=actual["counts"]["accepted"] - len(prefix),
                    stream_effective=sum(ops.get(q["token"], 0) for q in requests),
                    stream_productive=sum(ops.get(q["token"], 0) > 0 for q in requests),
                )
            summaries.append(item)
        save(dest / "states.json", summaries)
        print(
            case,
            source,
            len(summaries),
            [s for s in summaries if s["stall"]],
            flush=True,
        )


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = cli().parse_args()
    for case in a.cases:
        prepare(a, case)
