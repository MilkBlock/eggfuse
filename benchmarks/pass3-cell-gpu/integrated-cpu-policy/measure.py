"""Profile a single linked native executor and independent default-feature source on identical inputs."""

import argparse
import json
import sys
from contextlib import ExitStack
from pathlib import Path
from statistics import median
from time import perf_counter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "single-signature-frontier"))
from measure import setup, summarize
from study import read, session

MODES = {
    "legacy": (False, True, False, False, 0, False),
    "constant": (True, True, False, False, 0, False),
    "archive": (True, False, False, False, 0, False),
    "pages": (True, False, True, False, 0, False),
    "signed": (True, False, False, True, 0, False),
    "integrated": (True, False, True, True, 0, False),
    "typed": (True, False, True, True, 65536, False),
    "changed": (True, False, True, True, 262144, True),
    "typed256": (True, False, True, True, 262144, False),
}


ORIGINAL_ARMS = list(MODES)
for key in ("epochs", "sparse", "both", "all"):
    MODES[key] = (True, False, True, True, 262144 if key == "all" else 0, key == "all")


def query(base, name, admission, audit=False):
    guard, archive, pages, signed, n, delta = MODES[name]
    req = dict(
        base, audit=audit, archive_single_winners=archive, multi_root_pages=pages
    )
    if not guard:
        req.pop("early_guards", None)
    if signed:
        req.update(
            signature_frontier=dict(
                admission,
                typed_bytes=n,
                changed_ports=delta,
                changed_epochs=name in ("epochs", "both", "all"),
                fresh_build=name in ("sparse", "both", "all"),
            ),
            rows=dict(base["rows"], signature_frontier=True),
        )
    return req


def run(a):
    a.out.mkdir(parents=True, exist_ok=False)
    report = {}
    vdir = a.exp / "compact-vanilla-20261121"
    admission = read(HERE.parent / "single-signature-frontier/admission.json")[
        "parameters"
    ]
    for case in a.cases:
        prog, plan, _, req = setup(a, case)
        with session(vdir / "vanilla-audit", prog) as native:
            gold = native({"audit": True})
        with ExitStack() as ctx:
            cpu = ctx.enter_context(session(vdir / "vanilla", prog))
            infer = ctx.enter_context(session(a.native, prog, plan))
            arms = {
                "vanilla": {
                    "ms": [],
                    "wall_ms": [],
                    "rhs": gold["rhs_count"],
                    "runs": gold["runs"],
                }
            }
            for mode in a.arms:
                raw = infer(query(req, mode, admission, True))
                v = summarize(raw, gold)
                m = raw["multi"]
                v.update(
                    ms=[],
                    wall_ms=[],
                    setup_export_ms=[],
                    phase_ms=[],
                    pages=m["pages"],
                    packed=m["paged_tuples"],
                    raw_packets=m["counts"]["raw_tuples"],
                    root_child=raw["merge_child"]["counts"][5],
                    single_digest=raw["single"]["adaptive_rows"]["decision_digest"],
                    typed=m["single_epochs"]["typed"],
                    single_headers=v["rows"]["source_headers"],
                    single_issued=v["rows"]["emitted"],
                )
                v["frontier"] = {
                    k: sum(x[k] for x in v["work"].values())
                    for k in (
                        "pruned",
                        "source_reads",
                        "frame_hits",
                        "build_rows",
                        "dead_calls",
                    )
                }
                v.pop("work")
                v.pop("rows")
                assert (
                    v["packed"] == (v["raw_packets"] if MODES[mode][2] else 0)
                    and 100 * v["direct_cells"] >= 98 * v["fresh"]
                )
                if arms.keys() != {"vanilla"}:
                    expected = next(v for k, v in arms.items() if k != "vanilla")
                    for k in (
                        "single_winners",
                        "multi_winners",
                        "root_parents",
                        "root_ids",
                        "nested_ids",
                        "rhs",
                        "direct_cells",
                        "state_sha",
                        "cells",
                    ):
                        assert v[k] == expected[k], (case, mode, k)
                for prev, p in arms.items():
                    if prev == "vanilla":
                        continue
                    if (
                        MODES[mode][0] == MODES[prev][0]
                        and MODES[mode][3] == MODES[prev][3]
                        and mode not in ("epochs", "both", "all")
                        and prev not in ("epochs", "both", "all")
                    ):
                        for k in (
                            "multi",
                            "single_digest",
                            "raw",
                            "commits",
                            "physical",
                            "children",
                            "raw_packets",
                            "single_issued",
                        ):
                            assert p[k] == v[k], (case, mode, prev, k, p[k], v[k])
                arms[mode] = v
                del raw
            # The immutable page remains a live premise. Wrong template/version/withheld
            # recipes are rejected by the original allocator without supplying a replacement.
            faults = {}
            if "integrated" in arms:
                for f in (1, 2, 3):
                    bad = infer(
                        dict(query(req, "integrated", admission), multi_root_fault=f)
                    )
                    assert "no verified root recipe" in bad.get("source_error", "")
                    faults[f] = [bad["runs"], bad["source_error"]]
            modes = list(arms)
            for i in range(a.repeats + 1):
                j = i % len(modes)
                order = modes[j:] + modes[:j]
                for mode in order if i % 2 else reversed(order):
                    start = perf_counter()
                    raw = (
                        cpu({})
                        if mode == "vanilla"
                        else infer(query(req, mode, admission))
                    )
                    elapsed = (perf_counter() - start) * 1000
                    assert (
                        raw["state_sha"] == gold["state_sha"]
                        and raw["runs"] == gold["runs"]
                    )
                    v = arms[mode]
                    if mode != "vanilla":
                        assert bool(raw["single"]["committed"]) == MODES[mode][1]
                        assert (
                            v["root_allocated"] == raw["root_recipe"]["allocated"]
                            and raw["merge_child"]["counts"][5] == v["root_child"]
                        )
                        assert (
                            v["packed"] == raw["multi"]["paged_tuples"]
                            and v["single_issued"]
                            == raw["single"]["adaptive_rows"]["stats"]["emitted"]
                        )
                    if i:
                        v["ms"].append(raw["ms"])
                        v["wall_ms"].append(elapsed)
                        if mode != "vanilla":
                            v["setup_export_ms"].append(raw["pre_post_ms"])
                            v["phase_ms"].append(raw["phases_ms"])
            for v in arms.values():
                v["median_ms"] = median(v["ms"])
                v["wall_median_ms"] = median(v["wall_ms"])
        report[case] = {"arms": arms, "faults": faults}
        (a.out / "results.json").write_text(json.dumps(report, indent=1) + "\n")
        print(
            case, [(n, round(v["median_ms"], 2)) for n, v in arms.items()], flush=True
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("native", "exp", "out"):
        p.add_argument(k, type=Path)
    p.add_argument(
        "--cases",
        nargs="+",
        default=["sum-bits", "dot-product", "jacobi-1d", "conjugate-gradient"],
    )
    p.add_argument("--arms", nargs="+", choices=list(MODES), default=ORIGINAL_ARMS)
    p.add_argument("--repeats", type=int, default=5)
    run(p.parse_args())
