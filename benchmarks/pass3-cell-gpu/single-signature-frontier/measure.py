"""Replay original training sources for upper bounds, then evaluate frozen admission on held-out programs."""

import argparse
import importlib.util
import json
import sys
from contextlib import ExitStack
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


sys.path.insert(0, str(HERE.parent / "joint-witness"))
sys.path.insert(0, str(HERE.parent / "compact-recipes"))
from study import compare, digest, read, session

single = module("single_io", HERE.parent / "adaptive-row-policy/runner.py")
TRAIN = ("affine-twins", "clamped-ramp", "segmented-prefix", "window-laplacian")
TEST = ("sum-bits", "dot-product", "jacobi-1d", "conjugate-gradient")


def setup(a, case):
    large = a.exp / "compact-holdouts-20261121-v1" if case in TEST else None
    prog, plan, original, req = single.materialize(
        a.exp, a.out, case, 1703, "certified", large
    )
    tables = a.exp / "baked-port-packed-study-v1"
    root = a.out / (case + "-compact.json")
    root.write_text(
        json.dumps(
            {"encoding": "checked_slots", "control": "use", "forbid_fallback": True}
        )
    )
    req.update(
        multi_weights=str(tables / "sum-bits-1703-tied.json"),
        baked_codes=str(tables / "sum-bits-1703-tied.bin"),
        radius=0,
        baked_row_index=False,
        packed_lookup=True,
        root_config=str(root),
        early_guards="constants",
        multi_mode="rowdeltapairguardstackseallearned",
        rows={
            "action": 4,
            "max_rows": 1,
            "workers": 1,
            "batch": True,
            "verify": 2,
            "prefilter": 2,
        },
    )
    assert (
        not req["multi_residual"] and not read(Path(req["single_config"]))["residual"]
    )
    return prog, plan, original, req


def summarize(raw, gold):
    v = compare(raw, gold)
    assert (
        v["aligned"]
        and all(v["checks"].values())
        and v["rhs"] == v["neural_rhs"] == gold["rhs_count"]
    )
    assert 100 * v["direct_cells"] >= 98 * v["fresh"]
    v["single_winners"] = digest([t[:7] + t[9:] for t in raw["single"]["committed"]])
    v["multi_winners"] = digest(
        [
            {k: v for k, v in t.items() if k != "local_token_id"}
            for t in raw["multi"]["tickets"]
        ]
    )
    v["root_parents"] = digest([x[:2] + x[3:] for x in raw["root_recipe"]["commits"]])
    v["root_ids"] = digest([x[:5] for x in raw["root_recipe"]["fresh"]])
    v["nested_ids"] = digest(
        [
            (t["allocated"], t["template"], t["parent"]["ordinal"])
            for t in raw["merge_child"]["issued"]
            if t["allocated"] is not None
        ]
    )
    v["rows"] = raw["single"]["adaptive_rows"]["stats"]
    v["work"] = raw["multi"]["single_epochs"]["rules"]
    v["ms"] = []
    return v


def settings(a):
    if a.phase == "oracle":
        return {"off": None, "oracle": {"oracle": True}}
    if a.phase == "calibrate":
        return {
            "off": None,
            "resident": {"bytes": 0, "min_old": 16, "density": 50},
            "budget8": {"bytes": 8192, "min_old": 16, "density": 50, "scan_ratio": 1},
            "budget64": {"bytes": 65536, "min_old": 16, "density": 50, "scan_ratio": 2},
            "budget256": {
                "bytes": 262144,
                "min_old": 8,
                "density": 25,
                "scan_ratio": 4,
            },
            "select64": {"bytes": 65536, "min_old": 64, "density": 75, "scan_ratio": 1},
        }
    tuned = read(a.admission)
    return {
        "off": None,
        "resident": {
            "bytes": 0,
            "min_old": tuned["min_old"],
            "density": tuned["density"],
        },
        "bounded": tuned,
    }


def totals(v):
    keys = (
        "sources",
        "old",
        "admitted",
        "exact",
        "hashed",
        "existing",
        "existing_frame",
        "groups",
        "dead_groups",
        "dead_calls",
        "source_reads",
        "frame_hits",
        "build_rows",
        "pruned",
    )
    return {k: sum(x[k] for x in v["work"].values()) for k in keys}


def run(a):
    a.out.mkdir(parents=True, exist_ok=False)
    all_results = {}
    vanilla = a.exp / "compact-vanilla-20261121"
    for name in a.cases:
        prog, plan, original, req = setup(a, name)
        with session(vanilla / "vanilla-audit", prog) as audit:
            gold = audit({"audit": True})
        if name in TRAIN:
            assert all(
                gold[k] == read(original / (k + ".json"))
                for k in ("rhs", "writes", "resumes")
            )
        arms = settings(a)
        results = {}
        with ExitStack() as stack:
            cpu = stack.enter_context(session(vanilla / "vanilla", prog))
            infer = stack.enter_context(session(a.native, prog, plan))

            def query(mode, audit, req=req, arms=arms, infer=infer):
                x = dict(req, audit=audit)
                if arms[mode] is not None:
                    x.update(
                        signature_frontier=arms[mode],
                        rows=dict(req["rows"], signature_frontier=True),
                    )
                return infer(x)

            for mode in arms:
                o = query(mode, True)
                v = summarize(o, gold)
                results[mode] = v
                if mode != "off":
                    keys = (
                        "state_sha",
                        "cells",
                        "neural_rhs",
                        "direct_cells",
                        "single_winners",
                        "multi_winners",
                        "root_ids",
                        "root_parents",
                        "nested_ids",
                    )
                    if mode == "oracle":
                        keys += ("raw", "multi", "commits", "physical", "children")
                    assert all(results["off"][k] == v[k] for k in keys), (
                        name,
                        mode,
                        [k for k in keys if results["off"][k] != v[k]],
                    )
                del o
            if a.phase != "oracle":
                results["vanilla"] = {"ms": []}
                modes = ["vanilla", *arms]
                for i in range(a.repeats + 1):
                    off = i % len(modes)
                    order = modes[off:] + modes[:off]
                    for mode in order if i % 2 else order[::-1]:
                        v = cpu({}) if mode == "vanilla" else query(mode, False)
                        assert (
                            v["state_sha"] == gold["state_sha"]
                            and v["runs"] == gold["runs"]
                        )
                        if mode != "vanilla":
                            assert (
                                v["root_recipe"]["allocated"]
                                == results[mode]["root_allocated"]
                            )
                            assert (
                                v["single"]["adaptive_rows"]["stats"]
                                == results[mode]["rows"]
                            )
                        if i:
                            results[mode]["ms"].append(v["ms"])
                for v in results.values():
                    v["median_ms"] = median(v["ms"])
        all_results[name] = results
        (a.out / "results.json").write_text(json.dumps(all_results, indent=1) + "\n")
        v = results[
            "oracle"
            if a.phase == "oracle"
            else ("budget64" if a.phase == "calibrate" else "bounded")
        ]
        print(
            name,
            totals(v),
            {k: round(t.get("median_ms", 0), 2) for k, t in results.items()},
            flush=True,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase", choices=["oracle", "calibrate", "time"])
    for k in ("native", "exp", "out"):
        p.add_argument(k, type=Path)
    p.add_argument("--admission", type=Path)
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--cases", nargs="+", default=list(TRAIN))
    run(p.parse_args())
