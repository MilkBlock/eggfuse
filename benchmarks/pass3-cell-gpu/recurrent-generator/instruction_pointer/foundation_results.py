"""Export per-trial facts, actual costs and route attribution from native evidence."""

import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import torch

from foundation_study import CASES
from partner_index_worlds import args


def save(dest, items):
    keys = list(dict.fromkeys(k for item in items for k in item))
    with dest.open("w", newline="") as f:
        w = csv.DictWriter(f, keys, lineterminator="\n")
        w.writeheader()
        w.writerows(items)


def export(root):
    dest = Path("run-recall/foundation-memory")
    dest.mkdir(parents=True, exist_ok=True)
    trials = []
    routes = []
    manifest = {}
    facts = {}
    slots = []
    for case in CASES:
        for path in sorted((root / case).glob("*/result.json")):
            r = json.loads(path.read_text())
            name = path.parent.name
            st = r["stats"]
            assert (
                len(set(r["facts"])) == r["covered"]
                and abs(r["eps"] * r["wall"] - r["ops"]) < 1e-6
            )
            facts[case + "/" + name] = r["facts"]
            trials.append(
                dict(
                    case=case,
                    trial=name,
                    arm=r["arm"],
                    draw=r["draw"],
                    block=r["block"],
                    covered=r["covered"],
                    reference=r["reference"],
                    ops=r["ops"],
                    ept=r["ept"],
                    eps=r["eps"],
                    wall=r["wall"],
                    graph=r["graph"],
                    **st,
                )
            )
        primary = root / case / "ce-evidence-9734-0/result.json"
        audit = root / case / "audit-ce-evidence-9734-0"
        r = json.loads((audit / "result.json").read_text())
        assert r["graph"] == json.loads(primary.read_text())["graph"]
        events = json.loads((audit / "slots.json").read_text())
        assert sum(x["gain"] for x in events) == r["ops"]
        slots.extend(dict(case=case, **e) for e in events)
        for enabled in (False, True):
            xs = [e for e in events if (e["anchor"] is not None) == enabled]
            routes.append(
                dict(
                    case=case,
                    start="evidence" if enabled else "recipe",
                    attempts=len(xs),
                    paid=sum(e["uid"] is not None for e in xs),
                    productive=sum(e["gain"] > 0 for e in xs),
                    ops=sum(e["gain"] for e in xs),
                    **Counter(e["status"] for e in xs),
                )
            )
    corpus = []
    for source in sorted((root / "data").glob("*.pt")):
        for case, run, live, cell, paths in torch.load(
            source, map_location="cpu", weights_only=False
        ):
            corpus.append(
                {
                    "source": case,
                    "run": run,
                    "ports": live,
                    "rule": cell.rule,
                    "refs": cell.refs,
                    "arity": len(cell.refs),
                    "routes": len(paths),
                }
            )
    save(dest / "corpus.csv", corpus)
    for p in sorted(root.glob("*.pt")):
        manifest[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    save(dest / "native.csv", trials)
    save(dest / "routes.csv", routes)
    save(dest / "slots.csv", slots)
    (dest / "facts.json").write_text(json.dumps(facts, separators=(",", ":")) + "\n")
    (dest / "weights.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for f in ["training.csv", "hints.csv", "posterior.csv", "scale.csv", "higher.csv"]:
        shutil.copyfile(root / f, dest / f)


if __name__ == "__main__":
    export(args().out)
