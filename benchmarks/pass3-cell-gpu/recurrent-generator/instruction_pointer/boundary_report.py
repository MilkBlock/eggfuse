"""Package audited inputs and trial-level outcomes, including impossible entrances and failed partial runs."""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from shutil import copyfile

from recursive_train import read


def report(out, dest):
    dest.mkdir(parents=True, exist_ok=True)
    groups = defaultdict(list)
    for row in read(out / "boundaries.json"):
        groups[row["label"]].append(row)
    records = []
    for label, rows in groups.items():
        regions = [r["region"] for r in rows]
        own = [d for row in rows for d in row["own"]]
        probes = [d["trial"] for d in own if "trial" in d]
        reasons = Counter(d["status"] for d in own)

        def span(values):
            nums = list(values)
            return f"{min(nums)}..{max(nums)}" if nums else ""

        records.append(
            dict(
                boundary=label,
                witnesses=len(rows),
                steps=span(len(r["unit"]) for r in regions),
                external_slots=span(len(r["external"]) for r in regions),
                external_owners=span(len({p[0] for p in r["external"]}) for r in regions),
                late_external=span(len(r["late"]) for r in regions),
                version_obligations=span(len(r["problems"]) for r in regions),
                teacher_enter=sum(r["teacher_only"]["entry"] for r in regions),
                teacher_complete=sum(r["teacher_only"]["complete"] for r in regions),
                teacher_verified_replacements=sum("checks" in r.get("takeover", {}) for r in regions),
                teacher_effective=span(r["teacher_only"]["effective"] for r in regions),
                scheduled_model=len(own),
                model_enter=reasons["yes"],
                proven_no=reasons["no"],
                unknown=reasons["unknown"],
                tested_model_instances=len(probes),
                model_complete=sum(d["complete"] for d in probes),
                model_effective_per_test=span(d["effective"] for d in probes),
            )
        )
    with (dest / "boundaries.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(records)
    assert len(groups) == 8 and all(len(v) == 10 for v in groups.values())
    source = read(out / "dependency.json")
    assert all(set(w["left"]) & set(w["right"]) == set(w["shared"]) for w in source["witnesses"])
    assert read(out / "generator.json")["tape_identical"]
    assert read(out / "semantic.json")["status"] == "pass"
    for name in (
        "boundaries.json",
        "dependency.json",
        "catalog.json",
        "upstream.json",
        "generator.json",
        "versions.json",
        "exact.json",
        "semantic.json",
        "tests.log",
    ):
        copyfile(out / name, dest / name)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("dest", type=Path)
    a = p.parse_args()
    report(a.out, a.dest)
