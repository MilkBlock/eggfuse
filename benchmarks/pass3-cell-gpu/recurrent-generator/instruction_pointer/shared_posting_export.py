"""Export every original native result; aggregate repeated clocks within each draw."""

import hashlib
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from first_parent import records


def export(root, out):
    out.mkdir(parents=True, exist_ok=True)
    cases = ("fact", "loopfact", "sum-divisors")
    rows = []
    full = {}
    for case in cases:
        for path in sorted((root / case).glob("*/result.json")):
            r = json.loads(path.read_text())
            slug = path.parent.name
            page = int(slug.split("-")[0][4:]) if slug.startswith("page") else 8
            full[f"{case}/{slug}"] = r
            rows.append(
                dict(
                    case=case,
                    page=page,
                    arm=r["arm"],
                    draw=r["draw"],
                    block=r["block"],
                    covered=r["covered"],
                    reference=r["reference"],
                    coverage=r["covered"] / r["reference"],
                    ops=r["ops"],
                    paid=r["stats"]["paid"],
                    attempts=r["stats"]["attempts"],
                    ept=r["ept"],
                    eps=r["eps"],
                    wall=r["wall"],
                    graph=r["graph"],
                )
            )
    (out / "native.json").write_text(json.dumps(full, separators=(",", ":")) + "\n")
    records(out / "native.csv", rows)
    groups = defaultdict(list)
    for r in rows:
        groups[r["case"], r["page"], r["arm"]].append(r)
    summary = []
    for (case, page, arm), samples in sorted(groups.items()):
        draws = defaultdict(list)
        for r in samples:
            draws[r["draw"]].append(r)
        if any(len(group) != 2 for group in draws.values()):
            raise ValueError("incomplete paired clocks")
        spread = [
            (max(s["wall"] for s in group) - min(s["wall"] for s in group))
            / median(s["wall"] for s in group)
            for group in draws.values()
        ]
        summary.append(
            dict(
                case=case,
                page=page,
                arm=arm,
                draws=len(draws),
                replays=len(samples),
                **{
                    k: mean(mean(s[k] for s in g) for g in draws.values())
                    for k in (
                        "covered",
                        "coverage",
                        "ops",
                        "paid",
                        "ept",
                        "eps",
                        "wall",
                    )
                },
                median_paired_relative_range=median(spread),
            )
        )
    for key, r in full.items():
        if r["arm"] == "Bcompact":
            other = full[key.replace("Bcompact-", "B-")]
            assert all(
                r[k] == other[k]
                for k in ("facts", "graph", "receipts", "ops", "ept", "stats")
            )
    records(out / "summary.csv", summary)
    for name in ("binding", "higher", "diagnosis", "cost", "dispatch"):
        shutil.copyfile(root / f"{name}.csv", out / f"{name}.csv")
    import os

    source = Path(os.environ["ARTIFACT_ROOT"])
    files = [source / "multi-association" / f"{case}-ce-count.pt" for case in cases] + [
        source / "selective-partner/weights/9633-mixed-sparse.pt"
    ]
    manifest = {
        str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in files
    }
    (out / "weights.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    export(*map(Path, sys.argv[1:]))
