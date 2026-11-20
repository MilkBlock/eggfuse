"""Validate frozen evidence, package per-Run semantic/provenance digests and aggregate row costs."""

import argparse
import json
from pathlib import Path
from statistics import median

TRAIN = {"affine-twins", "clamped-ramp", "segmented-prefix", "window-laplacian"}
TEST = {"sum-bits", "dot-product", "jacobi-1d", "conjugate-gradient"}


def read(p):
    return json.loads(p.read_bytes())


def compact(raw, required):
    assert set(raw) == required
    out = {}
    for case, arms in raw.items():
        record = {}
        for name, arm in arms.items():
            if name == "vanilla":
                assert median(arm["ms"]) == arm["median_ms"]
                record[name] = arm
                continue
            assert arm["aligned"] and all(arm["checks"].values())
            assert (
                arm["neural_rhs"] == arm["rhs"]
                and arm["direct_cells"] * 100 >= 98 * arm["fresh"]
            )
            for k in (
                "cells",
                "single_winners",
                "multi_winners",
                "root_ids",
                "root_parents",
                "nested_ids",
                "state_sha",
            ):
                assert arm[k] == arms["off"][k]
            keys = (
                "rhs",
                "neural_rhs",
                "direct_cells",
                "fresh",
                "cells",
                "state_sha",
                "single_winners",
                "multi_winners",
                "root_ids",
                "root_parents",
                "nested_ids",
                "checks",
                "ms",
                "median_ms",
            )
            v = {k: arm[k] for k in keys if k in arm}
            if v["ms"]:
                assert median(v["ms"]) == v["median_ms"]
            v["addresses"] = arm["rows"]["source_headers"]
            v["issued"] = arm["rows"]["emitted"]
            v["stats"] = {}
            for counts in arm["work"].values():
                for k, count in counts.items():
                    v["stats"][k] = (
                        max(v["stats"].get(k, 0), count)
                        if k.startswith("peak_")
                        else v["stats"].get(k, 0) + count
                    )
            if name == "oracle":
                stats = v["stats"]
                assert (
                    stats["existing_frame"]
                    <= stats["existing"]
                    <= stats["hashed"]
                    <= stats["exact"]
                    <= stats["old"]
                    <= v["addresses"]
                )
                assert stats["dead_groups"] <= stats["groups"] and stats["pruned"] == 0
                assert (
                    v["addresses"] == arms["off"]["rows"]["source_headers"]
                    and v["issued"] == arms["off"]["rows"]["emitted"]
                )
                v["per_rule_upper"] = {
                    rid: [
                        x[k]
                        for k in (
                            "old",
                            "exact",
                            "hashed",
                            "existing",
                            "existing_frame",
                            "groups",
                            "dead_groups",
                            "dead_calls",
                        )
                    ]
                    for rid, x in arm["work"].items()
                    if x["old"]
                }
            if name not in ("off", "oracle"):
                stats = v["stats"]
                assert stats["pruned"] == stats["hashed"]
                assert (
                    arms["off"]["rows"]["source_headers"] - v["addresses"]
                    == stats["pruned"]
                )
                if name == "resident":
                    assert stats["peak_payload_bytes"] == 0
            record[name] = v
        out[case] = record
    return out


def package(e, dest):
    base = read(e / "single-signature-admission-v1/admission.json")
    pick = read(e / "single-signature-admission-v1/selection.json")
    files = [
        ("training-upper", "single-signature-train-v1", TRAIN),
        ("calibration", "single-signature-calibration-v1", TRAIN),
        ("heldout-upper", "single-signature-holdout-oracle-v1", TEST),
        ("timing", "single-signature-holdout-time-v1", TEST),
    ]
    for name, source, split in files:
        report = compact(read(e / source / "results.json"), split)
        if name == "timing":
            assert all(
                r["bounded"]["stats"]["peak_payload_bytes"] <= base["bytes"]
                for r in report.values()
            )
        (dest / (name + ".json")).write_text(json.dumps(report, indent=1) + "\n")
    assert set(pick["cases"]) == TRAIN and TRAIN.isdisjoint(TEST)
    (dest / "admission.json").write_text(
        json.dumps({"parameters": base, "training": pick}, indent=1) + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("exp", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    package(a.exp, a.out)
