"""Export compact summaries and checksum the actual weights and native trials."""

import csv
import hashlib
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median


def write(path, rows):
    with path.open("w") as f:
        w = csv.DictWriter(f, rows[0], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def export(src, dest):
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    for stage in ("frozen", "trained", "topology"):
        shutil.copyfile(src / f"{stage}.csv", dest / f"{stage}.csv")
        records = json.loads((src / f"{stage}-native.json").read_text())
        paired = defaultdict(list)
        for r in records:
            paired[r["kind"], r["arm"], r["i"], r["seed"], r["draw"]].append(r)
        groups = defaultdict(list)
        for (kind, arm, *_), repeats in paired.items():
            a, b = repeats
            assert all(
                a[k] == b[k] for k in ("facts", "graph", "ops", "stats", "receipts")
            )
            groups[kind, arm].append((a, b))
        for (kind, arm), cases in groups.items():
            rows.append(
                dict(
                    stage=stage,
                    kind=kind,
                    arm=arm,
                    cases=len(cases),
                    **{
                        m: mean(a[m] for a, b in cases)
                        for m in ("coverage", "ops", "ept")
                    },
                    eps=mean(r["eps"] for ab in cases for r in ab),
                    repeat_wall_spread=median(
                        abs(a["wall"] - b["wall"]) / mean((a["wall"], b["wall"]))
                        for a, b in cases
                    ),
                    generated=mean(a["stats"]["neural_tokens"] for a, b in cases),
                    paid=mean(a["stats"]["paid"] for a, b in cases),
                    complete=mean(a["stats"]["higher_completed"] for a, b in cases),
                    type_reject=mean(
                        a["receipts"]["rejected"].get("type", 0) for a, b in cases
                    ),
                )
            )
    write(dest / "execution.csv", rows)
    for name in ("historical-audit", "projection"):
        shutil.copyfile(src / f"{name}.csv", dest / f"{name}.csv")
    ps = json.loads((src / "projection-probe.json").read_text())
    rows = []
    for name in ("frozen", "mixed", "curriculum", "diverse"):
        for s in (71, 113):
            cases = [
                r for r in ps["retention"] if (r["trained"], r["seed"]) == (name, s)
            ]
            rows.append(
                {
                    "policy": name,
                    "seed": s,
                    "both": sum(r["both"] for r in cases),
                    "conflicts": len(cases),
                }
            )
    write(dest / "retention.csv", rows)
    rows = []
    for s in (71, 113):
        grads = [r[1:] for r in ps["grad"] if r[0] == s]
        rows.append(
            dict(
                seed=s,
                n=len(grads),
                **dict(
                    zip(
                        ("values", "relations", "Wrole", "Wquery"),
                        map(mean, zip(*grads)),
                        strict=True,
                    )
                ),
            )
        )
    write(dest / "gradients.csv", rows)
    choices = json.loads((src / "arity-choices.json").read_text())
    rows = []
    for name in ("frozen", "mixed", "curriculum", "diverse"):
        case = [r for r in choices if r["regime"] == name]
        rows.append(
            dict(
                regime=name,
                n=len(case),
                **{
                    k: mean(r[k] for r in case)
                    for k in case[0]
                    if k.startswith(("StartMark_", "Together_"))
                    or k in ("slots", "signed")
                },
            )
        )
    write(dest / "arity-choices.csv", rows)
    files = sorted(
        p for p in src.iterdir() if p.is_file() and p.name != "training-signatures.json"
    )
    files += [
        src.parent / "interface-role" / f"{n}-{s}{suffix}.pt"
        for n, suffix in (("transfer-mixed", ""), ("C", "-1680"))
        for s in (71, 113)
    ]
    manifest = {}
    for p in files:
        with p.open("rb") as f:
            manifest[str(p.relative_to(src.parent))] = hashlib.file_digest(
                f, "sha256"
            ).hexdigest()
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    export(Path(sys.argv[1]), Path(sys.argv[2]))
