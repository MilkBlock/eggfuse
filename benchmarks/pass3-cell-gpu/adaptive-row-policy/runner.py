"""Source-aligned complete CPU Cell passes; training capture and measured samples are separate."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "joint-witness"))
from evaluate import read, rpc, sealed_plans


def materialize(e, work, name, seed, regime, large=None):
    if large is not None:
        bundle = large / f"{name}-{seed}"
        req = read(bundle / "request.json")
        assert (
            regime == "certified"
            and not read(bundle / "single.json")["residual"]
            and req["multi_residual"] is False
        )
        for key in ("single_config", "multi_weights", "merge_config", "root_config"):
            req[key] = str(bundle / req[key])
        return (
            bundle / "program.json",
            bundle / "plans.json",
            work / f"{name}-source.json",
            req,
        )
    anchor = name in ("sum-bits", "dot-product")
    fam = e / "repair-bake-families-20261120" / name
    ref = e / "pass3-atlas-integration-20261120"
    prog = ref / name / "program.json" if anchor else fam / "program.json"
    image = ref / f"release-input-{name}" if anchor else fam / "input"
    original = ref / f"events-{name}" if anchor else fam / "observation"
    plan = work / f"{name}-plans.json"
    if not plan.exists():
        plan.write_text(json.dumps(sealed_plans(image), separators=(",", ":")))
    s = read(HERE.parent / "single-witness" / f"{regime}-{seed}.json")
    s.update(mode="learned", residual=regime != "certified")
    single = work / f"{name}-{seed}-{regime}.json"
    single.write_text(json.dumps(s, separators=(",", ":")))
    gate = read(HERE.parent / "joint-witness/weights" / f"nested-{seed}.json")
    merge = work / f"{name}-{seed}-merge.json"
    merge.write_text(
        json.dumps(
            {
                "program_sha256": read(prog)["sha256"],
                "weights": gate["weights"],
                "control": "learned",
            }
        )
    )
    root = work / f"{name}-{regime}-root.json"
    root.write_text(
        json.dumps(
            {
                "control": "use",
                "forbid_fallback": regime == "certified",
                "encoding": "shared_wire",
            }
        )
    )
    request = {
        "single_config": str(single),
        "multi_weights": str(HERE.parent / "ordinary-witness" / f"weights-{seed}.json"),
        "merge_config": str(merge),
        "root_config": str(root),
        "multi_mode": "stackseal3xlearned",
        "radius": 2,
        "multi_residual": False,
        "cap": 1000000,
    }
    return prog, plan, original, request


def digest(v):
    return hashlib.sha256(
        json.dumps(v, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def audit(r, original, require_coverage=True):
    if "source_error" in r:
        raise ValueError(r["source_error"])

    def unions(events):
        return [[v for v in row if v[0] == "union"] for row in events]

    if original.is_dir():
        assert (
            r["state_sha"]
            == hashlib.sha256((original / "state.json").read_bytes()).hexdigest()
        )
        for k in ("rhs", "resumes", "writes"):
            assert r[k] == read(original / f"{k}.json"), k
        assert unions(r["events"]) == unions(read(original / "events.json"))
        fields = (
            "ruleset",
            "epoch",
            "path",
            "iterations",
            "executed_bindings",
            "changed",
        )
        expected_schedule = [
            [step[k] for k in fields]
            for step in read(original / "report.json")["steps"]
        ]
        assert r["schedule"] == expected_schedule
    else:
        truth = read(original)
        for k in ("rhs", "writes", "resumes", "state_sha", "schedule"):
            assert r[k] == truth[k], k
        assert unions(r["events"]) == truth["unions"]
    rows = r["allocations"]
    total = len(rows)
    s, m, roots, merge = (
        r[k] for k in ("single", "multi", "root_recipe", "merge_child")
    )
    ordinals = [x[0] for x in s["committed"]] + [t["ordinal"] for t in m["tickets"]]
    assert (
        len(set(ordinals)) == len(ordinals)
        and min(ordinals) > 0
        and max(ordinals) <= total
    )
    by_id = {t[1]: t for t in r["cell_ids"] if not t[4]}
    primary = {c[0] for c in roots["fresh"]}
    nested = {t["allocated"] for t in merge["issued"] if t["allocated"] is not None}
    assert primary.isdisjoint(nested) and (primary | nested) <= by_id.keys()
    assert roots["applied"] == len(ordinals)
    if require_coverage:
        assert len(ordinals) >= 0.98 * total and len(primary | nested) >= 0.98 * len(
            by_id
        )
    return {
        "semantic": digest(
            [
                r["schedule"],
                r["rhs"],
                r["writes"],
                r["resumes"],
                unions(r["events"]),
                r["state_sha"],
            ]
        ),
        "roots": digest(roots["commits"]),
        "fresh": digest(roots["fresh"]),
        "merge": digest(merge["issued"]),
        "single": digest(s["committed"]),
        "multi": digest(m["tickets"]),
        "raw_single": s["adaptive_rows"]["decision_digest"],
        "raw_multi": m["raw_sha256"],
        "rhs": total,
        "learned_rhs": len(ordinals),
        "direct": len(primary | nested),
        "fresh_cells": len(by_id),
        "raw_root": roots["raw_hash"],
    }


def worker(a, prog, plan):
    return subprocess.Popen(
        [a.binary, prog, plan],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def capture(a):
    a.out.mkdir(parents=True, exist_ok=False)
    data = {}
    splits = read(a.exp / "repair-bake-families-20261120/collection.json")
    for name, info in splits.items():
        if info["split"] != "train":
            continue
        for regime in ("certified", "high"):
            for seed in a.seeds:
                prog, plan, original, req = materialize(
                    a.exp, a.out, name, seed, regime
                )
                proc = worker(a, prog, plan)
                try:
                    base = rpc(proc, dict(req, audit=True))
                    expected = audit(base, original)
                    for replicate in range(a.rounds):
                        setting = {
                            "action": 4,
                            "max_rows": 8,
                            "workers": 8,
                            "capture": True,
                            "seed": int(
                                (seed * 10 + replicate) * 13091204237039013 % (2**64)
                            ),
                        }
                        r = rpc(proc, dict(req, rows=setting, audit=False))
                        assert r["state_sha"] == base["state_sha"]
                        s = r["single"]["adaptive_rows"]
                        data[f"{name}/{regime}/{seed}/{replicate}"] = s["examples"]
                    detail = rpc(
                        proc,
                        dict(
                            req,
                            rows={"action": 7, "max_rows": 8, "workers": 8},
                            audit=True,
                        ),
                    )
                    got = audit(detail, original)
                    assert got == expected, (
                        name,
                        seed,
                        regime,
                        [k for k in got if got[k] != expected[k]],
                    )
                    (a.out / "reward.json").write_text(
                        json.dumps(data, separators=(",", ":"))
                    )
                    print(
                        name,
                        regime,
                        seed,
                        len(s["examples"]),
                        detail["single"]["adaptive_rows"]["stats"]["peak_workers"],
                        flush=True,
                    )
                finally:
                    proc.stdin.close()
                    proc.wait()


def modes(a, seed):
    arms = {
        "exact": None,
        "native": {},
        "direct-1": {"max_rows": 1, "workers": 1, "action": 0},
        "shared-1": {"max_rows": 1, "workers": 1, "action": 4},
        "cohorts": {"max_rows": 1, "workers": 1},
    }
    for width in (2, 4, 8):
        arms[f"direct-{width}"] = {
            "max_rows": width,
            "workers": width,
            "action": width.bit_length() - 1,
        }
        arms[f"shared-{width}"] = {
            "max_rows": width,
            "workers": width,
            "action": 4 + width.bit_length() - 1,
        }
    arms["serial-8"] = {"max_rows": 8, "workers": 1, "action": 7}
    for n in (1, 2, 4, 8):
        arms[f"page-{n}"] = {
            "action": 4 + n.bit_length() - 1,
            "max_rows": n,
            "workers": n,
            "batch": True,
        }
    for verifier in range(5):
        arms[f"verify-{verifier}"] = {
            "action": 4,
            "max_rows": 1,
            "workers": 1,
            "batch": True,
            "verify": verifier,
        }
    for prune in (1, 2):
        arms[f"prefilter-{prune}"] = {
            "action": 4,
            "max_rows": 1,
            "workers": 1,
            "batch": True,
            "verify": 2,
            "prefilter": prune,
        }
    if a.weights:
        for filename in sorted(a.weights.glob(f"{seed}-*-*.json")):
            model = read(filename)
            arm = f"{model['method']}-h{model['size']}-r{model['max_rows']}"
            arms[arm] = {
                "max_rows": model["max_rows"],
                "workers": model["max_rows"],
                "policy": model["weights"],
            }
    if a.vanilla_timed:
        arms["vanilla"] = None
    if a.arms:
        arms = {k: arms[k] for k in a.arms}
    return arms


def evaluate(a):
    a.out.mkdir(parents=True, exist_ok=False)
    report = {}
    for name in a.cases:
        if a.large is not None:
            if not a.vanilla:
                raise ValueError(
                    "provide the native vanilla auditor for the new workload"
                )
            call = subprocess.run(
                [a.vanilla, a.large / name / "program.json"],
                input='{"audit":true}\n',
                text=True,
                capture_output=True,
                check=True,
            )
            (a.out / f"{name}-source.json").write_text(call.stdout)
        for seed in a.seeds:
            for regime in a.regimes:
                prog, plan, original, req = materialize(
                    a.exp, a.out, name, seed, regime, a.large
                )
                if a.encoding:
                    root_cfg = a.out / f"{name}-{seed}-{regime}-root-encoding.json"
                    root_cfg.write_text(
                        json.dumps(
                            dict(read(Path(req["root_config"])), encoding=a.encoding)
                        )
                    )
                    req["root_config"] = str(root_cfg)
                proc = worker(a, prog, plan)
                vanilla = (
                    subprocess.Popen(
                        [a.vanilla_timed, prog],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    if a.vanilla_timed
                    else None
                )
                try:
                    reference = rpc(proc, dict(req, audit=True))
                    expected = audit(reference, original)
                    results = {}
                    arms = modes(a, seed)
                    for arm, setting in arms.items():
                        results[arm] = {"ms": []}
                        if arm in ("exact", "vanilla"):
                            continue
                        if (
                            arm not in ("native", "exact", "vanilla")
                            and a.best_verifier
                        ):
                            setting.update(verify=a.best_verifier, batch=True)
                        r = (
                            reference
                            if arm == "native"
                            else rpc(proc, dict(req, rows=setting, audit=True))
                        )
                        prefilter = bool(setting and setting.get("prefilter"))
                        got = audit(r, original, require_coverage=not prefilter)
                        if prefilter:
                            assert got["semantic"] == expected["semantic"]
                        else:
                            assert got == expected, (
                                name,
                                seed,
                                regime,
                                arm,
                                {
                                    k: (v, expected[k])
                                    for k, v in got.items()
                                    if v != expected[k]
                                },
                            )
                        v = r["single"]["adaptive_rows"]
                        results[arm].update(
                            audit=got,
                            stats=v["stats"],
                            wire_bytes=r["root_recipe"]["wire_bytes"],
                            verification=v.get("verification"),
                            raw_single=v["decision_digest"],
                            rhs=got["rhs"],
                            neural=got["learned_rhs"],
                            direct=got["direct"],
                            cells=got["fresh_cells"],
                        )
                    names = list(arms)
                    for i in range(a.rounds + 1):
                        order = (
                            names[(i * 5) % len(names) :]
                            + names[: (i * 5) % len(names)]
                        )
                        for arm in order if i % 2 == 0 else order[::-1]:
                            query = dict(req, audit=False)
                            if arm == "vanilla":
                                r = rpc(vanilla, {})
                                assert (
                                    r["state_sha"] == reference["state_sha"]
                                    and r["rhs_count"] == expected["rhs"]
                                )
                                if i:
                                    results[arm]["ms"].append(r["ms"])
                                continue
                            if arm == "exact":
                                query = {"baseline": True, "audit": False}
                            elif arm != "native":
                                query["rows"] = arms[arm]
                            r = rpc(proc, query)
                            assert r["state_sha"] == reference["state_sha"]
                            if arm != "exact":
                                assert (
                                    r["multi"]["neural_committed"]
                                    + len(r["single"]["committed"])
                                    == results[arm]["neural"]
                                )
                                assert (
                                    r["root_recipe"]["allocated"]
                                    + r["merge_child"]["counts"][5]
                                    == results[arm]["direct"]
                                )
                            if i:
                                results[arm]["ms"].append(r["ms"])
                    for arm, v in results.items():
                        v["median_ms"] = median(v["ms"])
                    report[f"{name}/{seed}/{regime}"] = {
                        "expected": expected,
                        "arms": results,
                    }
                    (a.out / "results.json").write_text(
                        json.dumps(report, indent=1) + "\n"
                    )
                    print(
                        name,
                        seed,
                        regime,
                        [(k, round(v["median_ms"], 1)) for k, v in results.items()],
                        flush=True,
                    )
                finally:
                    proc.stdin.close()
                    proc.wait()
                    if vanilla:
                        vanilla.stdin.close()
                        vanilla.wait()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("capture", "evaluate"))
    for key in ("binary", "exp", "out"):
        p.add_argument(key, type=Path)
    p.add_argument("--seeds", type=int, nargs="+", default=[1703, 1709])
    p.add_argument(
        "--cases",
        nargs="+",
        default=["sum-bits", "dot-product", "gemm-bias-relu", "stable-argmax"],
    )
    p.add_argument("--regimes", nargs="+", default=["certified", "high"])
    p.add_argument("--rounds", type=int, default=8)
    p.add_argument(
        "--encoding", choices=("full", "resident", "shared_wire", "checked_slots")
    )
    p.add_argument("--vanilla-timed", type=Path)
    p.add_argument("--best-verifier", type=int, default=0)
    p.add_argument("--large", type=Path)
    p.add_argument("--vanilla", type=Path)
    p.add_argument("--weights", type=Path)
    p.add_argument("--arms", nargs="+")
    a = p.parse_args()
    if a.mode == "capture":
        capture(a)
    else:
        evaluate(a)
