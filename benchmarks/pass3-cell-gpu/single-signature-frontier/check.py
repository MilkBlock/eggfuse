"""Validate the checked-in training split, budgets, upper bounds and full source/physical gates."""

import json
from pathlib import Path
from statistics import median

from package import TEST, TRAIN


def verify(d):
    files = {
        name: json.loads((d / (name + ".json")).read_bytes())
        for name in (
            "admission",
            "training-upper",
            "calibration",
            "heldout-upper",
            "timing",
        )
    }
    assert set(files["training-upper"]) == set(files["calibration"]) == TRAIN
    assert set(files["heldout-upper"]) == set(
        files["timing"]
    ) == TEST and TRAIN.isdisjoint(TEST)
    assert set(files["admission"]["training"]["cases"]) == TRAIN
    for group in ("calibration", "timing"):
        upper = files["training-upper" if group == "calibration" else "heldout-upper"]
        for case, arms in files[group].items():
            base = arms["off"]
            obs = upper[case]["oracle"]
            o = obs["stats"]
            assert (
                o["existing_frame"]
                <= o["existing"]
                <= o["hashed"]
                <= o["exact"]
                <= o["old"]
                <= base["addresses"]
            )
            assert o["dead_groups"] <= o["groups"] and o["dead_calls"] <= o["all_old"]
            assert (
                obs["issued"] == base["issued"]
                and obs["addresses"] == base["addresses"]
            )
            for name, v in arms.items():
                assert len(v["ms"]) == 5 and median(v["ms"]) == v["median_ms"]
                if name == "vanilla":
                    continue
                assert all(v["checks"].values()) and v["rhs"] == v["neural_rhs"]
                assert 100 * v["direct_cells"] >= 98 * v["fresh"]
                for key in (
                    "root_parents",
                    "single_winners",
                    "multi_winners",
                    "root_ids",
                    "nested_ids",
                    "state_sha",
                    "cells",
                    "fresh",
                ):
                    assert v[key] == base[key] == obs[key], (case, name, key)
                if name == "off":
                    continue
                assert (
                    0
                    <= v["stats"]["pruned"]
                    == base["addresses"] - v["addresses"]
                    <= o["hashed"]
                )
                if name == "resident":
                    assert v["stats"]["peak_payload_bytes"] == 0
                if name == "bounded":
                    assert (
                        v["stats"]["peak_payload_bytes"]
                        <= files["admission"]["parameters"]["bytes"]
                    )
    print(
        "Verified disjoint training/held-out schedules, all measured budgets, source endpoints, exact upper bounds and direct neural allocation."
    )


if __name__ == "__main__":
    verify(Path(__file__).resolve().parent)
