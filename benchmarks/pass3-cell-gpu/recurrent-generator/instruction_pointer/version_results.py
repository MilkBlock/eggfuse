"""Validate and summarize the saved raw native and policy trials."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

from recursive_train import binary, folder, read
from scaling_bake import save


def summarize(data, forks, out):
    for name in ("control", "control-dag"):
        control = read(out / f"{name}.json")
        if (
            not all(control["checks"].values())
            or control["accepted"] != control["paid"]
        ):
            raise ValueError("exact replay changed a native observation")
    if read(out / "semantic.json")["status"] != "pass":
        raise ValueError("sum-bits acceptance failed")

    def digest(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    files = {"native_executable": digest(binary(data))}
    for case in ("sum", "dot", "fact", "loopfact", "sum-divisors"):
        files[case] = {
            f: digest(folder(data, case) / f)
            for f in ("program.json", "tape.json", "memory.jsonl", "capture.json")
        }
    files["training_forks"] = {
        n: digest(forks / (n + ".jsonl"))
        for n in ("sum", "sum-roll", "grammar-benefit-fork-17118")
    }
    save(out / "inputs.json", files)
    groups = defaultdict(list)
    with (out / "frontier.jsonl").open() as raw:
        for row in map(json.loads, raw):
            groups[row["case"], row["pages"], row["arm"]].append(row)
    if len(groups) != 12:
        raise ValueError("incomplete policy experiment")
    table = []
    for (case, pages, arm), rows in sorted(groups.items()):
        a, b = rows
        if (
            a["block"] != 0
            or b["block"] != 1
            or any(
                a[k] != b[k]
                for k in ("state_sha", "covered", "facts", "signed_ops", "paid")
            )
        ):
            raise ValueError("paired outcome changed")
        frozen = groups[case, pages, "frozen"][0]
        eps = [r["eps"] for r in rows]
        wall = [r["wall"] for r in rows]
        full = [r["wall"] + r["runtime_setup_seconds"] + r["setup"] for r in rows]
        table.append(
            dict(
                case=case,
                pages=pages,
                arm=arm,
                covered=a["covered"],
                reference=a["reference"],
                paid=a["paid"],
                effective=a["signed_ops"],
                ept=a["ept"],
                eps=median(eps),
                eps_min=min(eps),
                eps_max=max(eps),
                wall_min=min(wall),
                wall_max=max(wall),
                cold_wall=median(full),
                cold_eps=median(a["signed_ops"] / t for t in full),
                same_graph=a["state_sha"] == frozen["state_sha"],
                added=len(set(a["facts"]) - set(frozen["facts"])),
                lost=len(set(frozen["facts"]) - set(a["facts"])),
            )
        )
    with (out / "frontier.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(table[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(table)
    if (
        groups["sum-divisors", 32, "frozen"][0]["paid"]
        != read(out / "neural.json")["paid"]
    ):
        raise ValueError("neural audit changed paid count")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for n in ("data", "forks", "out"):
        p.add_argument(n, type=Path)
    a = p.parse_args()
    summarize(**vars(a))
