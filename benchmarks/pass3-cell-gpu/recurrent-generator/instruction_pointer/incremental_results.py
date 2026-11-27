"""Require complete paired trajectories before summarising any implementation speedup."""

import csv
import hashlib
import itertools
import json
import sys
from pathlib import Path

CASES = ("fact", "loopfact", "sum-divisors")


def read(p):
    return json.loads(p.read_text())


def table(p, rows):
    with p.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def save(path, data):
    path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")


def same(a, b):
    for k in (
        "native_digest",
        "origins_digest",
        "receipts",
        "graph",
        "facts",
        "ops",
        "stats",
    ):
        if a[k] != b[k]:
            raise ValueError((a["case"], a["seed"], k))


def report(d, out):
    out.mkdir(exist_ok=True, parents=True)
    fit = []
    native_rows = []
    all_runs = []
    timing = []
    fitted_checks = []
    heldout = []
    cache = []
    batch = []
    activity = []
    checkpoints = {}
    params = {}
    controls = []
    op_profile = {}
    transfers = {}
    for case in CASES:
        forward = read(d / f"forward-{case}.json")
        for arm, seed in itertools.product("ABC", (71, 113)):
            stem = f"{case}-{arm}-{seed}"
            r = read(d / (stem + ".json"))
            assert r["signature"] == forward["signature"]
            ps = r["params"]
            params[stem] = {
                "params": ps,
                "forward": forward["forward"],
                "corpus": forward["targets"],
                "state_sources": r["sources"],
                "signature": r["signature"],
            }
            for pt in r["curve"]:
                tag = stem + f"-e{pt['epoch']}"
                checkpoints[tag] = hashlib.sha256(
                    (d / (tag + ".pt")).read_bytes()
                ).hexdigest()
                ev = read(d / ("eval-" + tag + ".json"))
                fit.append(
                    dict(
                        case=case,
                        arm=arm,
                        seed=seed,
                        states=r["states"],
                        targets=r["targets"],
                        registered=r["registered"],
                        enabled=r["enabled"],
                        forward_tensor_elements=sum(forward["forward"].values()),
                        backward_tensor_elements=sum(
                            x["numel"] for x in ps.values() if x["connected"]
                        ),
                        ever_nonzero=sum(x["nonzero"] for x in ps.values()),
                        changed=sum(x["changed"] for x in ps.values()),
                        **pt,
                        teacher_ce=ev["heldout"]["teacher"]["ce"],
                        autonomous_ce=ev["heldout"]["autonomous"]["ce"],
                    )
                )
        for f in sorted(d.glob(f"eval-{case}-*.json")):
            ev = read(f)
            for source, summary in ev["heldout"].items():
                heldout.append(
                    dict(case=case, model=ev["model"], source=source, **summary)
                )
            for r in ev["runs"]:
                if ev["model"].endswith("-e3") and r["cap"] == 256:
                    ref = read(
                        d / f"live-{case}-{ev['model']}-ref-{r['seed']}-256.json"
                    )
                    same(ref, r)
                    fitted_checks.append(
                        {
                            "case": case,
                            "model": ev["model"],
                            "seed": r["seed"],
                            "paid": r["stats"]["paid"],
                            "response": r["native_digest"],
                            "requests": r["origins_digest"],
                            "graph": r["graph"],
                        }
                    )
                native_rows.append(
                    {
                        "case": case,
                        "model": ev["model"],
                        "seed": r["seed"],
                        "cap": r["cap"],
                        "paid": r["stats"]["paid"],
                        "facts": r["covered"],
                        "reference": r["reference"],
                        "coverage": r["coverage"],
                        "ops": r["ops"],
                        "ept": r["ept"],
                        "eps": r["eps"],
                        "seconds": r["wall"],
                        "graph": r["graph"],
                    }
                )
                all_runs.append(r)
        for cap, seed in itertools.product(("256", "full"), (193, 307)):
            ref = read(d / f"live-{case}-sweep-ref-{seed}-{cap}.json")
            opt = read(d / f"live-{case}-sweep-cache-{seed}-{cap}.json")
            same(ref, opt)
            for r in (ref, opt):
                cache.append(
                    {
                        "case": case,
                        "method": r["arm"],
                        "seed": seed,
                        "cap": cap,
                        "wall": r["wall"],
                        "eps": r["eps"],
                        "ept": r["ept"],
                        "graph": r["graph"],
                        "paid": r["stats"]["paid"],
                        "covered": r["covered"],
                        "ops": r["ops"],
                        "response_hash": r["native_digest"],
                        "cache_counts": json.dumps(r["cache_counts"]),
                        "cache_seconds": json.dumps(r["cache_seconds"]),
                        "source_costs": json.dumps(r["cost"]),
                        "calls": json.dumps(r["calls"]),
                        "runtime_verify": r["native_verify_seconds"],
                        "transport": json.dumps(r["transport"]),
                    }
                )
        for rep in (0, 1):
            ref, opt = [
                read(d / f"live-{case}-sweep-{arm}-193-full-pair{rep}.json")
                for arm in ("ref", "cache")
            ]
            same(ref, opt)
            for r in (ref, opt):
                timing.append(
                    {
                        "case": case,
                        "order": rep,
                        "method": r["arm"],
                        "seed": r["seed"],
                        "wall": r["wall"],
                        "coverage": r["coverage"],
                        "eps": r["eps"],
                        "ept": r["ept"],
                        "paid": r["stats"]["paid"],
                        "ops": r["ops"],
                        "native_verify": r["native_verify_seconds"],
                        "transport": json.dumps(r["transport"]),
                        "costs": json.dumps(r["cost"]),
                        "cache_costs": json.dumps(r["cache_seconds"]),
                        "response": r["native_digest"],
                        "requests": r["origins_digest"],
                        "graph": r["graph"],
                    }
                )
        for prefix, device, capacity, rep in itertools.product(
            ("batch", "kvbatch"), ("cpu", "mps"), (1, 4), (0, 1)
        ):
            tag = f"{prefix}-{case}-{device}-{capacity}-{rep}"
            b = read(d / (tag + ".json"))
            for r in b["runs"]:
                same(r, read(d / f"live-{case}-sweep-ref-{r['seed']}-128.json"))
            batch.append(
                {
                    "case": case,
                    "stages": prefix,
                    "device": device,
                    "capacity": capacity,
                    "rep": rep,
                    "wall": b["wall"],
                    "eps": b["throughput"],
                    "paid": sum(r["stats"]["paid"] for r in b["runs"]),
                    "ops": sum(r["ops"] for r in b["runs"]),
                    "parent_candidates": b["metrics"]["parent_rows"],
                    "mean_parent_batch": b["metrics"]["parent_items"]
                    / b["metrics"]["parent_batches"],
                    "barriers": b["metrics"].get("readback_barriers", 0),
                    "up": b["metrics"].get("upload_bytes", 0),
                    "down": b["metrics"].get("download_bytes", 0),
                }
            )
            transfers[tag] = {
                "metrics": b["metrics"],
                "times": b["times"],
                "trajectories": [
                    (r["seed"], r["native_digest"], r["origins_digest"], r["graph"])
                    for r in b["runs"]
                ],
            }
        for model in ("sweep", "A", "B", "C"):
            q = read(d / f"windows-{case}-{model}.json")
            r = q["result"]
            all_runs.append(
                dict(r, case=case, window_model=model, native_digest=q["native_digest"])
            )
            for k, g in q["windows"].items():
                activity.append(
                    dict(
                        case=case,
                        model=model,
                        bucket=k,
                        **g,
                        ept=g["external_ops"] / g["external_paid"]
                        if g["external_paid"]
                        else "",
                        external_eps=g["external_ops"] / g["wall"],
                    )
                )
        for cap, seed in itertools.product((64, 256), (193, 307)):
            s = read(d / f"sparse-{case}-{cap}-{seed}.json")
            controls.append(
                {
                    "case": case,
                    "arm": "historical_sparse",
                    "cap": cap,
                    "seed": seed,
                    "paid": s["stats"]["paid"],
                    "covered": s["covered"],
                    "ops": s["ops"],
                    "ept": s["ept"],
                    "eps": s["eps"],
                    "index_slots": s["counts"].get("index_slots", 0),
                    "fallback": s["counts"].get("fallback_slots", 0),
                }
            )
        op_profile[case] = read(d / f"operators-{case}.json")
    hist = Path(__file__).parent / "run-recall/continuous-cell-stream/native.csv"
    for r in csv.DictReader(hist.open()):
        if r["arm"] in ("iid", "random", "history") and r["cap"] in ("64", "256"):
            controls.append(
                {
                    k: r[k]
                    for k in (
                        "case",
                        "arm",
                        "cap",
                        "seed",
                        "paid",
                        "covered",
                        "ops",
                        "ept",
                        "eps",
                    )
                }
                | {"index_slots": "", "fallback": ""}
            )
    table(out / "paired-timing.csv", timing)
    table(out / "trained-parity.csv", fitted_checks)
    table(out / "heldout.csv", heldout)
    table(out / "learning.csv", fit)
    table(out / "native.csv", native_rows)
    table(out / "cache.csv", cache)
    table(out / "batch.csv", batch)
    table(out / "activity.csv", activity)
    table(out / "controls.csv", controls)
    save(out / "parameters.json", params)
    save(out / "weights.json", checkpoints)
    save(out / "operators.json", op_profile)
    save(out / "batch-costs.json", transfers)
    metal = read(d / "metal-events-fact.json")
    for r in metal["runs"]:
        same(r, read(d / f"live-fact-sweep-ref-{r['seed']}-128.json"))
    save(out / "metal-events.json", metal)
    with (out / "executions.jsonl").open("w") as f:
        for r in all_runs:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    report(*map(Path, sys.argv[1:]))
