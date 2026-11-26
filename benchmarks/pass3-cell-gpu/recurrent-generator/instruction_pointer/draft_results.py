"""Publish paired runs and settled prefix credit from independent native replay."""

import argparse
import csv
import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from statistics import median

from metal_scaling import CASES
from recursive_coverage import snapshot
from recursive_train import binary, folder, read


def csvfile(path, rows):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def publish(out, data, dest):
    dest.mkdir(parents=True, exist_ok=True)
    pairs = []
    curves = []
    checkpoints = {}
    origins = {}
    ledgers = []
    raw = []
    for base, pattern in [
        (out / "paired", "*-s*-*-*"),
        (out, "cpu-s243-*-*"),
        (out / "fixture", "*-s*-*-*"),
        (out / "cut5", "*-s*-*-*"),
    ]:
        for work in sorted(base.glob(pattern)):
            device, _, tail = work.name.split("-", 2)
            arm, block = tail.rsplit("-", 1)
            if base == out and arm not in ("rule", "first", "later", "stream"):
                continue
            for p in sorted(work.glob("*.json")):
                if p.stem == "ref" or p.stem == "prefix":
                    continue
                x = read(p)
                case = x["case"]
                track = base.name if base != out else "stage"
                assert x["termination"] == "schedule_end"
                assert x["signed_ops"] == x["curve"][-1][-1]
                cs = x["work"]
                mark_total = cs.get("mark_draws", 0)
                subset = sorted(x["facts"])
                fid = hashlib.sha256(json.dumps(subset).encode()).hexdigest()
                pairs.append(
                    {
                        "track": track,
                        "device": device,
                        "arm": arm,
                        "block": block,
                        "case": case,
                        "covered": x["covered"],
                        "reference": x["reference"],
                        "fact_sha": fid,
                        "state_sha": x["state_sha"],
                        "paid": x["paid"],
                        "accepted": x["verdicts"].get("accepted", 0),
                        "effective": x["signed_ops"],
                        "ept": x["ept"],
                        "eps": x["cold_eps"],
                        "wall": x["cold_wall"],
                        "draws": mark_total,
                        "selected": sum(
                            len(r.get("selected", r["issued"]))
                            for r in x.get("pages", [])
                        ),
                        "direct_issued": len(x.get("receipts", [])),
                        "generated_survivor_exposures": sum(
                            len(r["uids"]) for r in x.get("pages", [])
                        ),
                        "draft_end": x.get("unissued", 0),
                        "unpublished": x.get("unpublished", 0),
                        "unissued_failed_dependency": cs.get(
                            "unissued_failed_dependency", 0
                        ),
                        "visits": cs.get("visits", 0),
                        "template_probes": cs.get("template_probe", 0),
                        "port_probes": cs.get("port_probe", 0),
                        "gpu_pivots": cs.get("device_pivot_visits", 0),
                        "higher_accepted": cs.get("instantiated", 0),
                        "higher_completed": cs.get("higher_completed", 0),
                        "statuses": json.dumps(x["verdicts"]),
                        "raw": str(p.relative_to(out)),
                    }
                )
                tape = work / (case + "-stream-multi") / "issued.json"
                tapehash = hashlib.sha256(tape.read_bytes()).hexdigest()
                if (case, tapehash) not in origins:
                    rep = json.loads(
                        subprocess.check_output(
                            [
                                binary(data),
                                "replay",
                                folder(data, case) / "program.json",
                                tape,
                                "audit",
                                "--ept-origins",
                            ]
                        )
                    )
                    origins[case, tapehash] = dict(rep["ept"]["origins"])
                credited = origins[case, tapehash]
                pairs[-1]["credited_requests"] = sum(v > 0 for v in credited.values())
                pairs[-1]["direct_credited_requests"] = sum(
                    credited.get(row[1], 0) > 0 for row in x.get("receipts", [])
                )
                pairs[-1]["direct_accepted"] = sum(
                    row[4] == 0 for row in x.get("receipts", [])
                )
                raw.append(
                    {
                        "path": str(p.relative_to(out)),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                )
                if (
                    (
                        arm in ("fifo", "set", "page")
                        and case == "sum-divisors"
                        and device == "cpu"
                    )
                    or track == "fixture"
                ) and block == "0":
                    ledgers.append(
                        {
                            "track": track,
                            "case": case,
                            "arm": arm,
                            "zero_primitive": x.get("zero_primitive", []),
                            "zero_higher": x.get("zero_higher", []),
                            "first_574": next(
                                (r for r in x["receipts"] if r[3] == 574), None
                            ),
                            "early_pages": x["pages"][:10],
                            "early_receipts": x["receipts"][:12],
                            "blocked_pages": sum(
                                bool(
                                    r["rules"]
                                    and r["rules"][0] == 375
                                    and 574 in r["rules"][1:]
                                    and not r["issued"]
                                )
                                for r in x["pages"]
                            ),
                            "nonhead_pages": sum(
                                bool(set(r["issued"]) - set(r["uids"][:1]))
                                for r in x["pages"]
                            ),
                        }
                    )
                if block != "0" or track not in ("paired", "stage"):
                    continue
                d = folder(data, case)
                for r, wall, inference, paid, attributed in x["curve"]:
                    if r not in {
                        1,
                        2,
                        3,
                        5,
                        8,
                        16,
                        32,
                        64,
                        128,
                        x["runs"] // 2,
                        x["runs"],
                    }:
                        continue
                    key = (case, tapehash, r)
                    if key not in checkpoints:
                        _, rep = snapshot(
                            data, d, "replay", tape, r, work / "prefix.json", ept=True
                        )
                        eff = rep["ept"]
                        checkpoints[key] = sum(eff["signed_external"]) + sum(
                            eff["signed_internal"]
                        )
                    effective = checkpoints[key]
                    if r == x["runs"]:
                        assert effective == x["signed_ops"]
                    curves.append(
                        {
                            "track": track,
                            "case": case,
                            "arm": arm,
                            "device": device,
                            "run": r,
                            "online_wall": wall,
                            "policy_seconds": inference,
                            "paid": paid,
                            "settled_ops": effective,
                            "terminal_credit_by_request_run": attributed,
                        }
                    )
    for device, arms, track in [
        (
            "cpu",
            ("fifo", "set", "relative", "page", "page-single", "page-multi"),
            "paired",
        ),
        (
            "mps",
            ("fifo", "set", "relative", "page", "page-single", "page-multi"),
            "paired",
        ),
        ("cpu", ("stream", "rule", "first", "later"), "stage"),
    ]:
        for arm in arms:
            for case in CASES:
                match = [
                    r
                    for r in pairs
                    if (r["device"], r["arm"], r["track"], r["case"])
                    == (device, arm, track, case)
                ]
                assert {r["block"] for r in match} == {"0", "1"}, (device, arm, case)
                assert (
                    len(
                        {
                            (r["state_sha"], r["fact_sha"], r["paid"], r["effective"])
                            for r in match
                        }
                    )
                    == 1
                )
    csvfile(dest / "runs.csv", pairs)
    csvfile(dest / "curves.csv", curves)
    agg = defaultdict(list)
    for r in read(out / "recall.json"):
        agg[r["case"], r["arm"], r["draws"]].append(r)
    recall = [
        {
            "case": c,
            "arm": a,
            "draws": n,
            "states": len(rs),
            "distinct_hits": sum(v["hits"] for v in rs),
            "verified": sum(v["known"] for v in rs),
            "ops": sum(v["ops"] for v in rs),
        }
        for (c, a, n), rs in agg.items()
    ]
    csvfile(dest / "recall.csv", recall)
    (dest / "ledgers.json").write_text(json.dumps(ledgers, indent=1) + "\n")
    (dest / "manifest.json").write_text(json.dumps(raw, indent=1) + "\n")
    (dest / "training.json").write_text((out / "training.json").read_text())
    for p in (out / "single.pt", out / "multi.pt"):
        print(p.name, hashlib.sha256(p.read_bytes()).hexdigest())
    for track in ["paired", "stage"]:
        for c in CASES:
            for a in (
                ("fifo", "set", "relative", "page", "page-single", "page-multi")
                if track == "paired"
                else ("stream", "rule", "first", "later")
            ):
                rows = [
                    r
                    for r in pairs
                    if (r["track"], r["device"], r["case"], r["arm"])
                    == (track, "cpu", c, a)
                ]
                if rows:
                    assert (
                        len(
                            {
                                (
                                    r["state_sha"],
                                    r["fact_sha"],
                                    r["effective"],
                                    r["paid"],
                                )
                                for r in rows
                            }
                        )
                        == 1
                    )
                    print(
                        c,
                        a,
                        rows[0]["covered"],
                        rows[0]["effective"],
                        rows[0]["paid"],
                        round(rows[0]["ept"], 3),
                        round(median(r["eps"] for r in rows), 2),
                    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("out", "data", "destination"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    publish(a.out, a.data, a.destination)
