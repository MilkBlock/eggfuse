"""Archive compact source hashes, per-arm wall samples, context labels, and the deployed policies."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def read(p):
    return json.loads(p.read_bytes())


def write(p, v):
    p.write_text(json.dumps(v, indent=1) + "\n")


def summarize(raw):
    result = {}
    for key, trial in raw.items():
        expected = trial["expected"]
        result[key] = {
            k: expected[k]
            for k in (
                "semantic",
                "raw_single",
                "raw_multi",
                "rhs",
                "fresh_cells",
                "direct",
            )
        }
        result[key].update(neural=expected["learned_rhs"], arms={})
        for name, data in trial["arms"].items():
            item = {"median_ms": data["median_ms"], "ms": data["ms"]}
            if "stats" in data:
                item.update(data["stats"])
                if arm_changed := data.get("audit"):
                    item["neural"] = arm_changed["learned_rhs"]
                    item["direct"] = arm_changed["direct"]
                    item["raw_single"] = arm_changed["raw_single"]
                    item["semantic"] = arm_changed["semantic"]
                    item["meets_coverage"] = (
                        100 * item["neural"] >= 98 * arm_changed["rhs"]
                        and 100 * item["direct"] >= 98 * arm_changed["fresh_cells"]
                    )
                if not name.startswith("prefilter"):
                    assert data["raw_single"] == expected["raw_single"]
            for field in ("wire_bytes", "verification"):
                if data.get(field) is not None:
                    item[field] = data[field]
            result[key]["arms"][name] = item
    return result


def frozen_source(e, name):
    if name in ("jacobi-1d", "conjugate-gradient"):
        source = read(e / "adaptive-row-large-integrated-v1" / f"{name}-source.json")
        ordered = [
            source[k]
            for k in ("schedule", "rhs", "writes", "resumes", "unions", "state_sha")
        ]
    else:
        if name in ("sum-bits", "dot-product"):
            source = e / "pass3-atlas-integration-20261120" / f"events-{name}"
        else:
            source = e / "repair-bake-families-20261120" / name / "observation"
        fields = (
            "ruleset",
            "epoch",
            "path",
            "iterations",
            "executed_bindings",
            "changed",
        )
        schedule = [
            [step[k] for k in fields] for step in read(source / "report.json")["steps"]
        ]
        unions = [
            [v for v in step if v[0] == "union"]
            for step in read(source / "events.json")
        ]
        graph = hashlib.sha256((source / "state.json").read_bytes()).hexdigest()
        ordered = [
            schedule,
            *(read(source / (k + ".json")) for k in ("rhs", "writes", "resumes")),
            unions,
            graph,
        ]
    digest = hashlib.sha256(
        json.dumps(ordered, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return {
        "sha256": digest,
        "runs": len(ordered[0]),
        "rhs": sum(step[4] for step in ordered[0]),
        "graph_sha256": ordered[-1],
    }


def package(e, dest):
    truth = {
        name: frozen_source(e, name)
        for name in (
            "sum-bits",
            "dot-product",
            "gemm-bias-relu",
            "stable-argmax",
            "jacobi-1d",
            "conjugate-gradient",
        )
    }
    write(dest / "source-hashes.json", truth)
    for filename, study in [
        ("width", "adaptive-row-width-study-v1"),
        ("policy", "adaptive-row-policy-study-v1"),
        ("pages", "adaptive-row-pages-v2"),
        ("verification", "adaptive-row-verify-v4"),
        ("larger", "adaptive-row-larger-v2"),
        ("integrated", "adaptive-row-integrated-v1"),
        ("large-integrated", "adaptive-row-large-integrated-v1"),
        ("prefilter", "adaptive-row-partial-v1"),
    ]:
        table = summarize(read(e / study / "results.json"))
        for key, row in table.items():
            source = truth[key.split("/")[0]]
            assert (
                row["semantic"] == source["sha256"] and row["rhs"] == source["rhs"]
            ), key
        write(dest / (filename + ".json"), table)
    write(dest / "controls.json", read(e / "adaptive-row-controls-v2/results.json"))
    write(
        dest / "heldout-cost.json",
        read(e / "adaptive-row-holdout-cost-v1/results.json"),
    )
    archive = {}
    for path in sorted((e / "adaptive-row-weights-v1").glob("*.json")):
        report = read(path)
        if (report["size"] == 8 and report["method"] == "policy-gradient") or (
            report["max_rows"] == 8
            and (report["method"] == "policy-gradient" or report["size"] == 8)
        ):
            archive[path.name] = report
    write(dest / "checkpoints.json", archive)
    labels = read(e / "adaptive-rows-labels-v1/reward.json")
    rows = {}
    for regime in ("high", "certified"):
        samples = [
            (max(1, round(2 ** (features[0] * 12) - 1)), costs)
            for key, events in labels.items()
            if key.split("/")[1] == regime
            for features, costs in events
        ]
        sizes = np.array([v[0] for v in samples])
        costs = np.array([v[1] for v in samples])
        actual = sizes > 1
        rows[regime] = {
            "samples": len(samples),
            "size_quantiles": np.percentile(sizes, [0, 50, 90, 99, 100]).tolist(),
            "single_address": int((sizes == 1).sum()),
            "nonsingle_fastest": np.bincount(
                costs[actual].argmin(1), minlength=8
            ).tolist(),
        }
    write(
        dest / "training-summary.json",
        {
            "programs": sorted({k.split("/")[0] for k in labels}),
            "reward_samples": rows,
            "measured_actions": 8,
            "seeds": [1703, 1709],
            "timed_repetitions_per_context": 1,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("experiments", type=Path)
    p.add_argument("dest", type=Path)
    a = p.parse_args()
    a.dest.mkdir(exist_ok=True)
    package(a.experiments, a.dest)
