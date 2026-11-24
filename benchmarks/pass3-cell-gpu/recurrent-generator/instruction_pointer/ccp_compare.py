"""Compare both transports with the same frozen neural policy and native binary."""

import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from recursive_coverage import Target, snapshot
from recursive_train import binary, folder, read
from transaction_native import execute
from txn_policy import ResponsePolicy


def compare(root, case):
    policy = "chain" if case.startswith("grammar-stride") else "learned"
    dataset = folder(root, case)
    results = {}
    tapes = []
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        goal = Target(
            read(dataset / "program.json"),
            snapshot(root, dataset, "reference", "-", None, path)[0],
        )
        seed = goal.match(snapshot(root, dataset, "reference", "-", 0, path)[0])
    for protocol in ("ctx1", "ccp-v0.1"):
        model = ResponsePolicy(root, policy)
        series = "ccp-comparison/" + protocol
        metrics = execute(
            root, case, study=model, series=series, seconds=180, protocol=protocol
        )
        out = root / series / (case + "-stream-multi")
        tapes.append(read(out / "issued.json"))
        results[protocol] = {
            k: v for k, v in metrics.items() if k not in ("trace", "guard_failures")
        }
        artifacts = {
            "runtime": binary(root),
            "program": dataset / "program.json",
            "compose": root / "recursive-agent/multi.pt",
            "field": root / "structured-retrieval/field.pt",
            "router": root
            / ("txn-chain-study" if policy == "chain" else "txn-study")
            / "model.pt",
        }
        results[protocol]["sha256"] = {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in artifacts.items()
        }
        results[protocol].update(
            mode="exclusive",
            policy=policy,
            derived=len(goal.match(read(out / "state.json")) - seed),
            reference=len(goal.gold) - len(seed),
        )
    assert tapes[0] == tapes[1]
    for k in (
        "paid",
        "derived",
        "signed_ops",
        "verdicts",
        "state_sha",
        "exact_endpoint",
        "runs",
    ):
        assert results["ctx1"][k] == results["ccp-v0.1"][k], (case, k)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("dest", type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    torch.set_num_threads(1)
    a.dest.mkdir(parents=True, exist_ok=True)
    for case in a.cases:
        out = compare(a.root, case)
        (a.dest / (case + ".json")).write_text(json.dumps(out, indent=2) + "\n")
        r = out["ccp-v0.1"]
        print(case, r["derived"], r["reference"], r["paid"], r["eps"], flush=True)
