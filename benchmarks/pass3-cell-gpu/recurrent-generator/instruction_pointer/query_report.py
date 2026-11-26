"""Summarize paired native runs, keeping signed proof, new operation and fact counts separate."""

import csv
import gzip
import hashlib
import json
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from statistics import mean, median

from metal_scaling import CASES
from query_witnesses import arguments
from recursive_train import folder, read


def save_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as out:
        w = csv.DictWriter(out, fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def summarize(a):
    d = a.dest
    d.mkdir(parents=True, exist_ok=True)
    for filename in ("witnesses.json", "witness-check.json", "semantic.json"):
        shutil.copyfile(a.out / filename, d / filename)
    probabilities = []
    native = []
    frozen = []
    costs = []
    manifest = {}
    for ckpt in sorted(a.out.rglob("*.pt")):
        manifest[str(ckpt.relative_to(a.out))] = hashlib.sha256(
            ckpt.read_bytes()
        ).hexdigest()
    (d / "weights.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for case in CASES:
        program = folder(a.data, case)
        tape = read(program / "tape.json")
        report = json.loads(
            subprocess.check_output(
                [
                    a.runtime_binary,
                    "replay",
                    program / "program.json",
                    program / "tape.json",
                    "audit",
                    "--ept-origins",
                ]
            )
        )
        gains = dict(report["ept"]["origins"])
        signed = {(q["run"], q["token"]) for q in tape["requests"]}
        baseline = None
        for arm in "ABCD":
            probes = read(a.out / "probes" / arm / case / "verdicts.json")
            for n in (4, 16, 64, 256):
                rows = [
                    (r, meta, owner, reason)
                    for r, meta, owner, reason in probes
                    if meta[0] <= n
                ]
                result = Counter(reason for _, _, _, reason in rows)
                # A proposed Higher entry has not established that its suffix completed.
                hits = {
                    (r, owner)
                    for r, meta, owner, reason in rows
                    if not meta[1] and reason == "match" and (r, owner) in signed
                }
                frozen.append(
                    dict(
                        case=case,
                        arm=arm,
                        budget=n,
                        signed_bindings=len(hits),
                        productive_bindings=sum(gains.get(k, 0) > 0 for _, k in hits),
                        witnessed_ops=sum(gains.get(k, 0) for _, k in hits),
                        proposals=len(rows),
                        **result,
                    )
                )
            paths = sorted(
                (a.out / "native-address" / case).glob(f"{arm}-k16-p2-b*/run.json")
            )
            pair = [read(f) for f in paths]
            assert len(pair) == 2 and all(
                x["termination"] == "schedule_end" for x in pair
            )
            x, y = pair
            assert all(
                x[k] == y[k]
                for k in ("state_sha", "facts", "verdicts", "paid", "signed_ops")
            )
            facts = set(x["facts"])
            if arm == "A":
                baseline = facts
            native.append(
                dict(
                    case=case,
                    arm=arm,
                    covered=len(facts),
                    reference=x["reference"],
                    lost_vs_A=len(baseline - facts),
                    new_vs_A=len(facts - baseline),
                    graph=x["state_sha"],
                    paid=x["paid"],
                    effective=x["signed_ops"],
                    EPT=x["ept"],
                    EPS=median(v["cold_eps"] for v in pair),
                    seconds_forward=x["cold_wall"],
                    seconds_reverse=y["cold_wall"],
                    scores=x["work"]["template_scores"],
                    pivots=x["work"]["device_pivot_visits"],
                    **x["verdicts"],
                )
            )
            for b, v in enumerate(pair):
                costs.append(
                    dict(
                        case=case,
                        arm=arm,
                        block=b,
                        wall=v["cold_wall"],
                        **v["device"],
                        **{
                            k: z for k, z in v["work"].items() if k.endswith("_seconds")
                        },
                    )
                )
    folds = [("donors", a.out)] + [
        (f.parent.name, f.parent)
        for f in sorted((a.out / "crossfit").glob("*/fit.json"))
    ]
    for name, folder_ in folds:
        for file in sorted(folder_.glob("prob-*.csv.gz")):
            arm = file.name.split("-")[1].split(".")[0]
            with gzip.open(file, "rt") as f:
                records = list(csv.DictReader(f))
            for case in ["all", *sorted({r["case"] for r in records})]:
                rows = [r for r in records if case == "all" or r["case"] == case]
                metrics = {}
                for k in (
                    "p_template",
                    "p_first",
                    "p_later",
                    "p_exact",
                    "p_class",
                    "p_binding_class",
                ):
                    xs = [float(r[k]) for r in rows if r[k]]
                    metrics[k] = mean(xs) if xs else None
                probabilities.append(
                    dict(split=name, case=case, arm=arm, n=len(rows), **metrics)
                )
    for name, rows in (
        ("probabilities", probabilities),
        ("native", native),
        ("frozen", frozen),
        ("costs", costs),
    ):
        save_csv(d / (name + ".csv"), rows)


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--dest", type=Path, required=True)
    summarize(p.parse_args())
