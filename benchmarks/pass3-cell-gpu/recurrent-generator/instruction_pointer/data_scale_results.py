"""Publish reproducible text records, terminal fact sets, timing pairs, and checkpoint digests."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

import numpy as np

from data_scale_train import LEVELS, subset_indices
from recursive_train import read


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def csvwrite(path, rows):
    with path.open("w") as f:
        w = csv.DictWriter(f, rows[0], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def corpus_levels(root):
    programs = read(root / "corpus.json")
    shards = [
        np.load(root / "programs" / f"{r['id']:04d}" / "plans.npy") for r in programs
    ]
    # Address a request by (program, tape offset). Count each physical supervision target once.
    plans = np.concatenate(shards)
    sizes = [len(s) for s in shards]
    families = np.repeat(np.arange(len(shards)), sizes)
    offsets = np.cumsum([0] + [r["requests"] for r in programs[:-1]])
    rows = []
    for n in LEVELS:
        ids = subset_indices(sizes, len(plans), n)
        chosen = plans[ids]
        pp = families[ids]
        refs = chosen[:, 1:]
        named = (refs + offsets[pp, None])[refs >= 0]
        widths = (refs >= 0).sum(1)
        rows.append(
            {
                "plans": n,
                "programs": len(np.unique(pp)),
                "witnessed_named_requests": len(np.unique(named)),
                "program_runs": len(np.unique(np.c_[pp, chosen[:, 0]], axis=0)),
                "lengths": [int(x) for x in np.bincount(widths, minlength=5)[1:]],
            }
        )
    return rows


def collect(root, dst):
    dst.mkdir(exist_ok=True, parents=True)
    save(dst / "levels.json", corpus_levels(root))
    fit = []
    runs = []
    weights = []
    for label, d in (
        ("passes", root),
        ("iso1568", root / "fixed1568"),
        ("fine", root / "fine"),
    ):
        for p in sorted(d.glob("s*/*/fit.json")):
            fit.append(dict(budget=label, **read(p)))
            for wt in p.parent.glob("*.pt"):
                weights.append(
                    {"path": str(wt.relative_to(root)), "sha256": digest(wt)}
                )
        for p in sorted(d.glob("s*/*/*-b*.json")):
            if p.name.startswith("cpu-"):
                backend = "legacy-cpu"
            elif label == "passes" and p.name.startswith(
                ("meter-matched-", "meter-stream-", "meter-scalar-")
            ):
                backend = p.name.split("-")[1]
            else:
                continue
            row = read(p)
            if row["termination"] != "schedule_end" or row["covered"] != len(
                set(row["facts"])
            ):
                raise ValueError(p)
            runs.append(
                dict(
                    budget=label,
                    seed=int(p.parent.parent.name[1:]),
                    backend=backend,
                    **row,
                )
            )
    for name in ("tiny", "tiny-4096"):
        for p in sorted((root / name).glob("*.pt")):
            weights.append({"path": str(p.relative_to(root)), "sha256": digest(p)})
    if len(runs) != 496:
        raise ValueError(("missing native runs", len(runs)))
    (dst / "runs.jsonl").write_text(
        "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in runs)
    )
    grouped = defaultdict(list)
    for r in runs:
        grouped[
            tuple(
                r[k] for k in ("budget", "seed", "size", "dataset", "case", "backend")
            )
        ].append(r)
    pairs = []
    for key, rr in grouped.items():
        if len(rr) != 2 or {r["block"] for r in rr} != {0, 1}:
            raise ValueError(key)
        a, b = rr
        if (a["state_sha"], a["paid"], a["facts"]) != (
            b["state_sha"],
            b["paid"],
            b["facts"],
        ):
            raise ValueError(("unstable pair", key))
        row = dict(zip(("budget", "seed", "size", "dataset", "case", "backend"), key))
        row.update(
            facts=a["covered"],
            ref=a["reference"],
            paid=a["paid"],
            effective=a["signed_ops"],
            ept=a["ept"],
            eps=median(x["cold_eps"] for x in rr),
            cold_min=min(x["cold_wall"] for x in rr),
            cold_max=max(x["cold_wall"] for x in rr),
            graph=a["state_sha"],
        )
        pairs.append(row)
    csvwrite(dst / "pairs.csv", pairs)
    device = []
    for r in runs:
        if r["backend"] != "stream":
            continue
        group = {
            x["backend"]: x
            for x in runs
            if all(
                r[k] == x[k]
                for k in ("budget", "seed", "size", "dataset", "case", "block")
            )
        }
        scalar, cpu = group["scalar"], group["matched"]
        i = r["inference"]
        device.append(
            {
                "size": r["size"],
                "seed": r["seed"],
                "case": r["case"],
                "block": r["block"],
                "same_graph": all(
                    q["state_sha"] == r["state_sha"] for q in (scalar, cpu)
                ),
                "same_paid": all(q["paid"] == r["paid"] for q in (scalar, cpu)),
                "same_verdicts": all(
                    q["verdicts"] == r["verdicts"] for q in (scalar, cpu)
                ),
                "stream_wall": r["cold_wall"],
                "scalar_mps_wall": scalar["cold_wall"],
                "cpu_wall": cpu["cold_wall"],
                "stream_waits": i["metal_command_buffer_waits"],
                "scalar_mps_waits": scalar["inference"]["metal_command_buffer_waits"],
                "boundary_reads": i["boundary_readbacks"],
                "issue_reads": i.get("issue_readbacks", 0),
                "seal_reads": i.get("seal_readbacks", 0),
                "retries": i.get("overflow_restarts", 0),
                "active_marks": i["useful_mark_lanes"],
                "pages": i["pages"],
                "max_batch": i["largest_edit_batch"],
                "allocated_lanes": i["allocated_mark_lanes"],
                "upload_bytes": i["upload_bytes"],
                "download_bytes": i["download_bytes"],
                "index_updates": i["index_row_updates"],
                "index_submit_seconds": i["index_update_submit_seconds"],
                "growth_copy_bytes": i.get("growth_copy_bytes", 0),
            }
        )
    csvwrite(dst / "device.csv", device)
    profiles = []
    for path in sorted(root.glob("s*/*/profile-stream-*.json")):
        row = read(path)
        profiles.append(
            dict(
                case=row["case"],
                block=row["block"],
                size=row["size"],
                graph=row["state_sha"],
                **row["inference"],
            )
        )
    if len(profiles) != 8:
        raise ValueError(("missing paired publication profiles", len(profiles)))
    csvwrite(
        dst / "publication-profile.csv",
        [
            {
                k: r[k]
                for k in (
                    "case",
                    "block",
                    "size",
                    "graph",
                    "index_row_updates",
                    "profiled_publications",
                    "index_update_submit_seconds",
                    "publication_mps_interval_seconds",
                )
            }
            for r in profiles
        ],
    )
    save(dst / "training.json", fit)
    save(dst / "weights.json", weights)
    save(
        dst / "tiny.json",
        {
            str(p.relative_to(root)): read(p)
            for n in ("tiny", "tiny-4096")
            for p in (root / n).glob("*.json")
        },
    )
    for src, dest in (
        ("held-metrics.json", "held-metrics.json"),
        ("corpus.json", "corpus.json"),
        ("held/corpus.json", "held-corpus.json"),
        ("page-parity.json", "page-parity.json"),
    ):
        save(dst / dest, read(root / src))
    old = [
        json.loads(line)
        for line in Path("run-recall/response-edit/runs.jsonl").read_text().splitlines()
    ]
    refs = {x["case"]: x for x in old if x["arm"] == "A"}
    base = []
    for name in sorted({r["case"] for r in runs}):
        ref = refs[name]
        sets = set().union(*(set(r["facts"]) for r in runs if r["case"] == name))
        base.append(
            {
                "case": name,
                "historical_covered": ref["covered"],
                "historical_ept": ref["ept"],
                "historical_cold_eps": ref["cold_eps"],
                "all_new_arms_union": len(sets),
                "facts_outside_historical": sorted(sets - set(ref["facts"])),
            }
        )
    save(dst / "high-recall.json", base)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("destination", type=Path)
    a = p.parse_args()
    collect(a.root, a.destination)
