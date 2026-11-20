"""Compare frozen source schedules with matched clock-free and instrumented runs."""

import argparse
import hashlib
import importlib.util
import json
from contextlib import ExitStack
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "integrated_headers", HERE.parent / "integrated-cpu-policy/measure.py"
)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
MODES = {
    "compiled": 0,
    "static": 1,
    "publication": 2,
    "delta": 3,
    "postings": 4,
    "stale": 5,
    "direct": 6,
    "direct-postings": 7,
}
PHASES = (
    "base_features",
    "empty_check",
    "source_snapshot",
    "watermark_filter",
    "signature_frontier",
    "feature_groups",
)


def recipe(a, case):
    root = (
        a.exp
        / (
            "extra-pass3-transfer-v1"
            if case in ("deriche", "3mm")
            else "compact-holdouts-20261121-v1"
        )
        / f"{case}-1703"
    )
    v = base.read(root / "request.json")
    p = root / "program.json"
    assert hashlib.sha256(p.read_bytes()).hexdigest() == v["source_sha256"]
    if case in ("deriche", "3mm"):
        meta = base.read(root.parent / "manifest.json")[case]
        assert (
            meta["program"] == v["source_sha256"]
            and hashlib.sha256((root / "plans.json").read_bytes()).hexdigest()
            == meta["plans"]
        )
    for k in ("single_config", "merge_config"):
        v[k] = str(root / v[k])
    assert (
        not v["multi_residual"] and not base.read(Path(v["single_config"]))["residual"]
    )
    cfg = a.out / f"{case}-root.json"
    cfg.write_text(
        json.dumps(
            {"control": "use", "forbid_fallback": True, "encoding": "checked_slots"}
        )
    )
    tables = a.exp / "baked-port-packed-study-v1"
    v.update(
        root_config=str(cfg),
        multi_weights=str(tables / "sum-bits-1703-tied.json"),
        baked_codes=str(tables / "sum-bits-1703-tied.bin"),
        packed_lookup=True,
        baked_row_index=False,
        radius=0,
        multi_generation="complete",
        multi_mode="rowdeltapairguardstackseal2xlearned",
        early_guards="constants",
        rows={
            "action": 4,
            "max_rows": 1,
            "workers": 1,
            "batch": True,
            "verify": 2,
            "prefilter": 2,
        },
    )
    v = base.query(
        v,
        "all",
        base.read(HERE.parent / "single-signature-frontier/admission.json")[
            "parameters"
        ],
    )
    v.update(
        forward={
            "columns": 2,
            "budget": 4 << 20,
            "existence": True,
            "freshness": True,
            "min_candidates": 8,
        },
        atom_constraints=2,
        tiered_ports={
            "primary": True,
            "columns": True,
            "evidence_views": 1,
            "bytes": 1 << 20,
        },
    )
    return p, root / "plans.json", v


def summarize(v, gold):
    z = base.summarize(v, gold)
    s = v["single"]["adaptive_rows"]
    row = z.pop("rows")
    z.pop("work")
    z.update(
        header_view=v["header_view"],
        sealed=s["decision_digest"],
        source_count=row["source_headers"],
        issued=row["emitted"],
        raw_multi=v["multi"]["counts"]["raw_tuples"],
        pages=v["multi"]["pages"],
        snapshot_builds=row["snapshot_builds"],
        snapshot_hits=row["snapshot_reuses"],
        postings=v["multi"]["single_epochs"].get("header_router", {}),
        ms=[],
    )
    return z


def run(a):
    a.out.mkdir(parents=True, exist_ok=False)
    identity = {
        "binary_sha256": hashlib.sha256(a.native.read_bytes()).hexdigest(),
        "build_manifest_sha256": hashlib.sha256(
            (a.native.parent / "build.json").read_bytes()
        ).hexdigest(),
        "cases": a.cases,
        "modes": a.modes,
        "timed_repetitions": a.repeats,
        "profile_repetitions": a.clocks,
        "seed": 1703,
    }
    (a.out / "identity.json").write_text(json.dumps(identity, indent=1) + "\n")
    result = {}
    for case in a.cases:
        prog, plan, q = recipe(a, case)
        vdir = a.exp / "compact-vanilla-20261121"
        with base.session(vdir / "vanilla-audit", prog) as sess:
            gold = sess({"audit": True})
        modes = a.modes
        with ExitStack() as stack:
            infer = stack.enter_context(base.session(a.native, prog, plan))
            cpu = stack.enter_context(base.session(vdir / "vanilla", prog))

            def call(name, audit=False, clocks=False, request=q, worker=infer):
                return worker(
                    dict(
                        request,
                        header_mode=MODES[name],
                        audit=audit,
                        rows=dict(request["rows"], profile=clocks),
                    )
                )

            arms = {
                "vanilla": {"ms": [], "runs": gold["runs"], "rhs": gold["rhs_count"]}
            }
            first = None
            for name in modes:
                raw = call(name, True)
                v = summarize(raw, gold)
                del raw
                if first is None:
                    first = v
                else:
                    for k in (
                        "sealed",
                        "raw_multi",
                        "single_winners",
                        "multi_winners",
                        "cells",
                        "root_ids",
                        "nested_ids",
                        "root_parents",
                        "raw",
                        "multi",
                        "commits",
                        "physical",
                        "children",
                        "issued",
                        "direct_cells",
                        "state_sha",
                    ):
                        assert v[k] == first[k], (case, name, k, v[k], first[k])
                assert (
                    v["rhs"] == v["neural_rhs"] == gold["rhs_count"]
                    and 100 * v["direct_cells"] >= 98 * v["fresh"]
                )
                arms[name] = v
            for lap in range(a.clocks + 1):
                for name in modes if lap % 2 else reversed(modes):
                    if name == "stale":
                        continue
                    r = call(name, clocks=True)
                    assert r["state_sha"] == gold["state_sha"]
                    s = r["single"]["adaptive_rows"]
                    z = {
                        k: n / 1e6
                        for k, n in zip(PHASES, s["inner_headers"], strict=True)
                    }
                    z.update(
                        inference=r["ms"],
                        single_headers=s["phase_ns"][0] / 1e6,
                        single_score=s["phase_ns"][1] / 1e6,
                        single_issue=s["phase_ns"][2] / 1e6,
                        validation_attach=s["phase_ns"][3] / 1e6,
                    )
                    if "snapshot_ns" in s:
                        z.update(
                            snapshot_hit=s["snapshot_ns"][0] / 1e6,
                            snapshot_rebuild=s["snapshot_ns"][1] / 1e6,
                        )
                    if lap:
                        arms[name].setdefault("clocks", []).append(z)
            names = ["vanilla", *[n for n in modes if n != "stale"]]
            for lap in range(1 + a.repeats):
                i = lap % len(names)
                seq = names[i:] + names[:i]
                for name in seq if lap % 2 else reversed(seq):
                    raw = cpu({}) if name == "vanilla" else call(name)
                    assert (
                        raw["state_sha"] == gold["state_sha"]
                        and raw["runs"] == gold["runs"]
                    )
                    if name != "vanilla":
                        assert (
                            raw["root_recipe"]["allocated"]
                            == arms[name]["root_allocated"]
                            and raw["single"]["adaptive_rows"]["stats"]["emitted"]
                            == arms[name]["issued"]
                        )
                    if lap:
                        arms[name]["ms"].append(raw["ms"])
            for name in names:
                z = arms[name]
                z["median_ms"] = median(z["ms"])
                if "clocks" in z:
                    z["median_clock_ms"] = {
                        f: median(v[f] for v in z["clocks"]) for f in z["clocks"][0]
                    }
        result[case] = arms
        (a.out / "results.json").write_text(json.dumps(result, indent=1) + "\n")
        print(
            case,
            [
                (
                    n,
                    round(v.get("median_ms", 0), 2),
                    round(v.get("median_clock_ms", {}).get("signature_frontier", 0), 2),
                )
                for n, v in arms.items()
            ],
            flush=True,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("native", "exp", "out"):
        p.add_argument(k, type=Path)
    p.add_argument(
        "--cases", nargs="+", default=["sum-bits", "dot-product", "3mm", "deriche"]
    )
    p.add_argument(
        "--modes",
        nargs="+",
        choices=list(MODES),
        default=["compiled", "static", "publication", "delta", "postings", "stale"],
    )
    p.add_argument("--clocks", type=int, default=3)
    p.add_argument("--repeats", type=int, default=5)
    run(p.parse_args())
