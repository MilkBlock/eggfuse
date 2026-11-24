"""Measure typed Cell transactions independently of changes to proof discovery."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import torch

from recursive_coverage import Target, snapshot
from recursive_train import binary, folder, read
from stream_guard import Study
from stream_native import execute as json_run

CASES = (
    "grammar-7300147",
    "grammar-layout-832749",
    "fact",
    "loopfact",
    "sum-divisors",
    "cyk801",
)
SERIES = {
    "json-lsh": "guard-p8-delta",
    "typed-lsh": "txn-baseline",
    "learned": "txn-learned",
    "always": "txn-always",
    "random-address": "txn-random-address",
    "chain": "txn-chain",
}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def run(root, case, policy, series):
    from transaction_native import execute
    from txn_policy import ResponsePolicy

    if policy in ("json-lsh", "typed-lsh"):
        study = Study(bits=8, symmetric=True, delta_buckets=True)
    else:
        study = ResponsePolicy(root, policy)
    if policy == "json-lsh":
        return json_run(root, case, "stream", 120, "multi", series=series, study=study)
    return execute(root, case, study=study, seconds=120, series=series)


def pairs(root, dest, case):
    d = folder(root, case)
    gold = read(d / "capture.json")["state_sha"]
    result = []
    for i in range(4):
        entry = {}
        order = ["json-lsh", "typed-lsh", "learned"]
        # Reverse runtime pair every round and rotate learned arm's position.
        if i % 2:
            order.reverse()
        if i in (1, 2):
            order.insert(1, order.pop(order.index("learned")))
        for policy in order:
            m = run(root, case, policy, "txn-timing/" + policy)
            entry[policy] = {
                k: m[k]
                for k in (
                    "wall",
                    "ept",
                    "eps",
                    "paid",
                    "signed_ops",
                    "state_sha",
                    "termination",
                )
            }
            entry[policy]["exact_endpoint"] = m["state_sha"] == gold
        assert entry["typed-lsh"]["paid"] == entry["json-lsh"]["paid"]
        assert entry["typed-lsh"]["state_sha"] == entry["json-lsh"]["state_sha"]
        for mode in ("reference", "replay") if i % 2 == 0 else ("replay", "reference"):
            start = perf_counter()
            m = json.loads(
                subprocess.check_output(
                    [
                        binary(root),
                        mode,
                        d / "program.json",
                        "-" if mode == "reference" else d / "tape.json",
                        "time",
                    ]
                )
            )
            assert m["state_sha"] == gold
            entry[mode] = {
                "wall": perf_counter() - start,
                "engine_seconds": m["seconds"],
            }
        result.append(entry)
        save(dest / f"{case}-pairs.json", result)
        print(
            case, i + 1, {k: round(v["wall"], 3) for k, v in entry.items()}, flush=True
        )


def report(root, dest, cases):
    results = []
    for case in cases:
        d = folder(root, case)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            ref, ref_metrics = snapshot(root, d, "reference", "-", None, path)
            initial, _ = snapshot(root, d, "reference", "-", 0, path)
            goal = Target(read(d / "program.json"), ref)
            seed = goal.match(initial)
            assert len(goal.match(ref)) == len(goal.gold)
        controls = {}
        for policy, series in SERIES.items():
            w = root / series / (case + "-stream-multi")
            if (
                policy in ("always", "random-address", "chain")
                and not (w / "metrics.json").exists()
            ):
                continue
            m = read(w / "metrics.json")
            if any(v < 0 for k, v in m["work"].items() if k.endswith("_seconds")):
                raise ValueError(f"negative phase time for {policy} on {case}")
            hits = len(goal.match(read(w / "state.json")) - seed)
            row = {
                k: v
                for k, v in m.items()
                if k not in ("trace", "guard_failures", "runtime_events")
            }
            row.update(
                policy=policy,
                derived=hits,
                reference=len(goal.gold) - len(seed),
                reference_commits=ref_metrics["matches"],
            )
            if policy in ("json-lsh", "typed-lsh"):
                controls[policy] = row
            results.append(row)
        json_tape, typed_tape = [
            read(root / SERIES[key] / (case + "-stream-multi") / "issued.json")
            for key in ("json-lsh", "typed-lsh")
        ]
        assert json_tape == typed_tape, case
        left, right = controls.values()
        for k in ("state_sha", "paid", "runs", "signed_ops", "derived", "verdicts"):
            assert left[k] == right[k], (case, k)
        for k in ("bucket_items", "visits", "tuple_scored"):
            assert left["work"].get(k, 0) == right["work"].get(k, 0), (case, k)
    save(dest / "results.json", results)
    paths = {
        "runtime": binary(root),
        "compose": root / "recursive-agent/multi.pt",
        "fields": root / "structured-retrieval/field.pt",
        "policy": root / "txn-study/model.pt",
        "chain_policy": root / "txn-chain-study/model.pt",
    }
    paths.update({case: folder(root, case) / "program.json" for case in cases})
    save(
        dest / "digests.json",
        {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in paths.items()},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("dest", type=Path)
    p.add_argument("action", choices=["pairs", "report", *SERIES])
    p.add_argument("cases", nargs="*")
    args = p.parse_args()
    torch.set_num_threads(1)
    args.dest.mkdir(parents=True, exist_ok=True)
    cases = args.cases or CASES
    if args.action == "report":
        report(args.root, args.dest, cases)
    else:
        for case in cases:
            if args.action == "pairs":
                pairs(args.root, args.dest, case)
            else:
                m = run(args.root, case, args.action, SERIES[args.action])
                print(case, args.action, m["paid"], m["state_sha"], flush=True)
