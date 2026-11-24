"""Four counterbalanced independent CCP rollouts per workload with offline cost alignment."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from statistics import median
from time import perf_counter

import numpy as np
import torch

from protocol_learning import LearningPolicy
from protocol_model import ProtocolNet
from recursive_coverage import Target, snapshot
from recursive_train import binary, folder, read
from transaction_native import execute
from txn_policy import ResponsePolicy

CASES = (
    "grammar-25112473",
    "grammar-stride2-25112473",
    "grammar-stride3-split-7300147",
    "fact",
    "sum-divisors",
    "cyk801",
)
ORDERS = ("ABDC", "BCAD", "CDBA", "DACB")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def run(root, dest, cases):
    torch.set_num_threads(1)
    for case in cases:
        dataset = folder(root, case)
        work = root / "protocol-ablation" / case
        work.mkdir(exist_ok=True, parents=True)
        path = work / "align.json"
        ref, _ = snapshot(root, dataset, "reference", "-", None, path)
        target = Target(read(dataset / "program.json"), ref)
        seed = target.match(snapshot(root, dataset, "reference", "-", 0, path)[0])
        total = len(target.gold) - len(seed)
        route = "chain" if "stride" in case else "learned"
        artifact = {
            "binary": binary(root),
            "program": dataset / "program.json",
            "compose": root / "recursive-agent/multi.pt",
            "encoder": root / "structured-retrieval/field.pt",
            "route": root
            / ("txn-chain-study" if route == "chain" else "txn-study")
            / "model.pt",
            "learner": dest / "model.pt",
        }
        info = {
            "case": case,
            "protocol": "0.1",
            "mode": "exclusive",
            "reference": total,
            "sha256": {k: digest(v) for k, v in artifact.items()},
            "arms": {a: [] for a in "ABCD"},
            "controls": [],
            "cost_curve": {},
        }
        traces = {a: [] for a in "ABCD"}
        for repeat, order in enumerate(ORDERS):
            for arm in order:
                net = ProtocolNet().eval()
                net.load_state_dict(torch.load(dest / "model.pt", weights_only=True))
                study = (
                    ResponsePolicy(root, route)
                    if arm == "A"
                    else LearningPolicy(root, arm, net, route=route)
                )
                series = f"protocol-ablation/{case}/{arm}"
                out = root / series / (case + "-stream-multi")
                m = execute(root, case, study=study, series=series, seconds=240)
                derived = len(target.match(read(out / "state.json")) - seed)
                paid = m["paid"] + m["work"].get("neural_controls", 0)
                trace = m.pop("trace")
                if not traces[arm]:
                    # Reconstruct each recorded point offline. No reference hints to the generator.
                    runs = len(trace)
                    stops = sorted(
                        {
                            runs,
                            *range(1, min(5, runs) + 1),
                            *np.linspace(1, runs, min(12, runs), dtype=int).tolist(),
                        }
                    )
                    points = []
                    for i in stops:
                        state, _ = snapshot(
                            root, dataset, "replay", out / "issued.json", i, path
                        )
                        points.append(
                            {"run": i, "derived": len(target.match(state) - seed)}
                        )
                    assert points[-1]["derived"] == derived
                    info["cost_curve"][arm] = points
                traces[arm].append(trace)
                m.update(
                    derived=derived,
                    controls_paid=paid - m["paid"],
                    all_paid=paid,
                    ept_with_controls=m["signed_ops"] / max(1, paid),
                    typed_value_tags=dict(getattr(study, "types_seen", {})),
                    position=order.index(arm) + 1,
                    repeat=repeat + 1,
                )
                # Keep stage-level counters, but omit the potentially large per-guard histogram.
                m.pop("guard_failures")
                if repeat:
                    first = info["arms"][arm][0]
                    for key in ("state_sha", "paid", "all_paid", "derived", "verdicts"):
                        assert m[key] == first[key], (case, arm, key)
                info["arms"][arm].append(m)
                print(case, repeat, arm, derived, paid, round(m["wall"], 3), flush=True)
            controls = {}
            for mode in (
                ("reference", "replay") if repeat % 2 == 0 else ("replay", "reference")
            ):
                t = perf_counter()
                report = json.loads(
                    subprocess.check_output(
                        [
                            binary(root),
                            mode,
                            dataset / "program.json",
                            dataset / "tape.json" if mode == "replay" else "-",
                            "time",
                        ]
                    )
                )
                assert (
                    report["state_sha"] == read(dataset / "capture.json")["state_sha"]
                )
                controls[mode] = perf_counter() - t
            info["controls"].append(controls)
        for arm, points in info["cost_curve"].items():
            for p in points:
                rows = [tr[p["run"] - 1] for tr in traces[arm]]
                p.update(
                    elapsed=median(r["elapsed"] for r in rows),
                    visits=rows[0]["visits"],
                    requests=rows[0]["paid"],
                    tokens=rows[0]["paid"] + rows[0]["controls"],
                )
        dump(dest / (case + ".json"), info)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("dest", type=Path)
    ap.add_argument("cases", nargs="*")
    a = ap.parse_args()
    run(a.root, a.dest, a.cases or CASES)
