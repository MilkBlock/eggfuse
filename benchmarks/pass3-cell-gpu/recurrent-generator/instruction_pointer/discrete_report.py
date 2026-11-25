"""Collect independent native executions and paired timing summaries without mixing pilot runs."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
from shutil import copyfile
from statistics import median


def read(path):
    return json.loads(path.read_text())


def collect(raw, report):
    report.mkdir(parents=True, exist_ok=True)
    for name in (
        "fit",
        "frozen",
        "holdout",
        "suffix-audit",
        "guard-certificate",
        "transfer",
        "late-entry-certificate",
        "native-evaluation",
        "address-diagnosis",
        "semantic",
    ):
        copyfile(raw / f"{name}.json", report / f"{name}.json")
    held = read(raw / "holdout.json")
    training = set(read(raw / "fit.json")["signatures"])
    if any(record["signature"] in training for record in held["cases"].values()):
        raise ValueError("evaluation signature occurs in this training set")
    for file, expected in held["frozen_sha"].items():
        src = raw / file
        if hashlib.sha256(src.read_bytes()).hexdigest() != expected:
            raise ValueError(f"checkpoint changed after freezing: {file}")
        copyfile(src, report / file)
    primitive = report / "primitive-fit"
    primitive.mkdir(exist_ok=True)
    for name, digest in read(raw / "transfer.json")["weights"]["primitive"].items():
        src = raw / "primitive-fit" / name
        if hashlib.sha256(src.read_bytes()).hexdigest() != digest:
            raise ValueError(f"primitive-only weights changed: {name}")
        copyfile(src, primitive / name)
    copyfile(raw / "primitive-fit" / "fit.json", primitive / "fit.json")
    milestones = {p.stem: read(p) for p in sorted(raw.glob("milestone-*.json"))}
    (report / "milestones.json").write_text(json.dumps(milestones, indent=2) + "\n")
    rows = {}
    for file in sorted(raw.glob("*__*.json")):
        row = read(file)
        if row["protocol"] != "ccp-v0.1":
            raise ValueError(file)
        rows[file.stem] = row
    with (report / "independent.jsonl").open("w") as out:
        for run, row in rows.items():
            print(json.dumps(dict(run_id=run, **row), separators=(",", ":")), file=out)
    columns = (
        "case",
        "method",
        "n",
        "covered",
        "reference",
        "paid",
        "effective",
        "ept",
        "eps",
        "wall_median",
        "wall_min",
        "wall_max",
    )
    with (report / "paired.csv").open("w") as out:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(columns)
        groups = {}
        for run, row in rows.items():
            name, suffix = run.split("__")
            method, block = suffix.rsplit("_b", 1)
            if block not in ("0", "1", "2", "3", "4", "7"):
                continue
            if "reference-source-order" in method and row["termination"] != "schedule_end":
                continue
            groups.setdefault((name, method), []).append(row)
        for (case, method), group in sorted(groups.items()):
            r = group[0]
            if (
                len(
                    {(v["coverage_sha"] if "coverage_sha" in v else v["state_sha"], v["paid"]) for v in group}
                )
                != 1
            ):
                continue  # Outcome-changing time limits retain all individual records in JSONL.
            walls = [v["cold_wall"] for v in group]
            writer.writerow(
                (
                    case,
                    method,
                    len(group),
                    r["covered"],
                    r["reference"],
                    r["paid"],
                    r["signed_ops"],
                    r["ept"],
                    median(v["cold_eps"] for v in group),
                    median(walls),
                    min(walls),
                    max(walls),
                )
            )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("raw", type=Path)
    p.add_argument("report", type=Path)
    args = p.parse_args()
    collect(args.raw, args.report)
