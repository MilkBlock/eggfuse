"""Check and time a two-factor treatment against an independently built source e-graph."""

import argparse
import hashlib
import json
import sys
from contextlib import ExitStack
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "compact-recipes"))
from catalog import check as check_catalog
from study import compare, digest, read, session


def settings(a):
    prefix = "rowdelta" + a.pair + "guardstackseallearned"
    return {
        "multi_mode": prefix,
        "rows": {
            "action": 4,
            "max_rows": 1,
            "workers": 1,
            "batch": True,
            "verify": 2,
            "prefilter": 2,
        },
    }


def summarize(output, gold):
    v = compare(output, gold)
    assert v["aligned"] and all(v["checks"].values()), v
    assert (
        v["rhs"] == v["neural_rhs"] == gold["rhs_count"]
        and 100 * v["direct_cells"] >= 98 * v["fresh"]
    )
    m = output["multi"]
    r = output["root_recipe"]
    ch = output["merge_child"]
    v.update(
        multi_sources=digest(
            [
                {k: v for k, v in t.items() if k != "local_token_id"}
                for t in m["tickets"]
            ]
        ),
        root_parents=digest([t[:2] + t[3:] for t in r["commits"]]),
        root_ids=digest([t[:5] for t in r["fresh"]]),
        nested_ids=digest(
            [
                (t["allocated"], t["template"], t["parent"]["ordinal"])
                for t in ch["issued"]
                if t["allocated"] is not None
            ]
        ),
        rules=m["transaction_guards"],
        counts=m["counts"],
        per_rule={
            str(i): {
                k: x[k] for k in ("raw", "root_visits", "signature_visits", "checks")
            }
            for i, x in enumerate(m["rule_profile"])
            if x["calls"]
        },
        ms=[],
    )
    assert v["counts"]["exhausted"] == 0
    return v


def run(a):
    a.out.mkdir(parents=True, exist_ok=False)
    report = {}
    root_path = a.out / "root.json"
    root_path.write_text(
        json.dumps(
            {"control": "use", "forbid_fallback": True, "encoding": "checked_slots"}
        )
    )
    for case in a.cases:
        key = f"{case}-{a.seed}"
        b = a.bundles / key
        prog = b / "program.json"
        req = read(b / "request.json")
        assert req["source_sha256"] == hashlib.sha256(prog.read_bytes()).hexdigest()
        assert (
            not req["multi_residual"] and not read(b / req["single_config"])["residual"]
        )
        for k in ("single_config", "merge_config"):
            req[k] = str(b / req[k])
        req.update(
            settings(a),
            multi_weights=str(a.tables / f"{key}-tied.json"),
            radius=0,
            baked_codes=str(a.tables / f"{key}-tied.bin"),
            packed_lookup=True,
            baked_row_index=False,
            root_config=str(root_path),
        )
        modes = {
            "off": {},
            "constants": {"early_guards": "constants"},
            "local": {"early_guards": "local"},
        }
        if a.controls:
            modes.update(
                stale={"early_guards": "stale"}, foreign={"early_guards": "foreign"}
            )
        with ExitStack() as stack:
            with session(a.vanilla / "vanilla-audit", prog) as audit:
                gold = audit({"audit": True})
            cpu = stack.enter_context(session(a.vanilla / "vanilla", prog))
            infer = stack.enter_context(session(a.native, prog, b / "plans.json"))
            arms = {
                "vanilla": {"ms": [], "runs": gold["runs"], "rhs": gold["rhs_count"]}
            }
            for mode, cfg in modes.items():
                out = infer(
                    dict(
                        req, **cfg, multi_mode="profile" + req["multi_mode"], audit=True
                    )
                )
                q = summarize(out, gold)
                q["catalog"] = check_catalog(b, q["rules"])
                if mode != "off":
                    base = arms["off"]
                    keys = [
                        "state_sha",
                        "cells",
                        "neural_rhs",
                        "fresh",
                        "direct_cells",
                        "rhs",
                        "multi_sources",
                        "root_parents",
                        "root_ids",
                        "nested_ids",
                    ]
                    if mode in ("stale", "foreign"):
                        keys.extend(
                            [
                                "raw",
                                "wire_hash",
                                "commits",
                                "physical",
                                "multi",
                                "children",
                            ]
                        )
                        assert (
                            sum(
                                r["work"]["invalid_receipts"]
                                for r in q["rules"].values()
                            )
                            > 0
                        )
                    assert all(q[k] == base[k] for k in keys), (
                        case,
                        mode,
                        [(k, q[k], base[k]) for k in keys if q[k] != base[k]],
                    )
                arms[mode] = q
            names = ["vanilla", "off", "constants", "local"]
            for n in range(a.repeats + 1):
                off = n % len(names)
                order = names[off:] + names[:off]
                for mode in order if n % 2 == 0 else order[::-1]:
                    v = (
                        cpu({})
                        if mode == "vanilla"
                        else infer(dict(req, **modes[mode], audit=False))
                    )
                    assert (
                        v["state_sha"] == gold["state_sha"]
                        and v["runs"] == gold["runs"]
                    )
                    if mode != "vanilla":
                        assert (
                            v["root_recipe"]["allocated"]
                            == arms[mode]["root_allocated"]
                        )
                        assert v["multi"]["counts"] == arms[mode]["counts"]
                    if n:
                        arms[mode]["ms"].append(v["ms"])
            for arm in names:
                arms[arm]["median_ms"] = median(arms[arm]["ms"])
        report[key] = arms
        (a.out / "results.json").write_text(json.dumps(report, indent=1) + "\n")
        print(
            key,
            [
                (
                    k,
                    round(arms[k]["median_ms"], 2),
                    arms[k].get("counts", {}).get("raw_tuples"),
                )
                for k in names
            ],
            flush=True,
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("native", "vanilla", "bundles", "tables", "out"):
        p.add_argument(k, type=Path)
    p.add_argument(
        "--cases",
        nargs="+",
        default=["sum-bits", "dot-product", "jacobi-1d", "conjugate-gradient"],
    )
    p.add_argument("--seed", type=int, default=1703)
    p.add_argument("--repeats", type=int, default=6)
    p.add_argument("--controls", action="store_true")
    p.add_argument("--pair", choices=["pair", "corr"], default="pair")
    run(p.parse_args())
