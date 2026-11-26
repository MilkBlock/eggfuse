"""Summarize physical replays, receipts, sparse prompt trials, and paired terminal facts."""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from continuation_audit import arguments
from continuation_data import sources
from recursive_train import read


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def table(path, rows):
    with path.open("w") as f:
        w = csv.DictWriter(f, rows[0], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def collect(a):
    dest = a.destination
    dest.mkdir(parents=True, exist_ok=True)
    data = []
    for case, src, d, tape in sources(a):
        meta = read(a.out / f"corpus-{case}-{src}.json")
        req = read(tape)["requests"]
        byid = {q["token"]: q["run"] for q in req}
        cross = sum(
            any(
                byid.get(p["address"]["token"], q["run"]) < q["run"]
                for p in q["parents"]
            )
            for q in req
        )
        prev = {}
        changed = 0
        for line in (a.out / f"corpus-{case}-{src}.jsonl").open():
            frame = json.loads(line)
            for addr, row in frame["updates"]:
                key = addr["token"], addr["op"]
                changed += key in prev and prev[key] != row["version"]
                prev[key] = row["version"]
        data.append(
            dict(
                **meta,
                requests_with_earlier_signed_parent=cross,
                revised_named_versions=changed,
            )
        )
    data.append(read(a.out / "corpus-sum-rejected.json"))
    save(dest / "data.json", data)
    save(dest / "fragment-labels.json", read(a.out / "endpoints.json"))
    rows = []
    paths = []
    for p in sorted((a.out / "audit").glob("*.json")):
        z = read(p)
        pages = z["pages"]
        run = z["run"]
        rows.append(
            {
                "case": p.stem,
                "dispatch": Counter(p["reason"] for p in pages),
                "after_run1_attempts": sum(
                    len(q["attempts"]) for q in pages if q["run"] > 1
                ),
                "after_run1_completed_marks": sum(
                    ok for q in pages if q["run"] > 1 for _, ok in q["attempts"]
                ),
                "after_run1_insert": sum(
                    p["insert_hazard"] for p in pages if p["run"] > 1
                ),
                "after_run1_delete": sum(
                    p["delete_hazard"] for p in pages if p["run"] > 1
                ),
                "signed_ops": run["signed_ops"],
                "paid": run["paid"],
                "verdicts": run["verdicts"],
                "runs": run["runs"],
                "termination": run["termination"],
            }
        )
        paths.extend(dict(arm=p.stem, **q) for q in pages)
    save(dest / "audit.json", rows)
    with (dest / "pages.jsonl").open("w") as f:
        for q in paths:
            f.write(json.dumps(q, separators=(",", ":")) + "\n")
    rows = []
    groups = defaultdict(list)
    for p in sorted((a.out / "native").glob("s*/*/b*/*.json")):
        if p.name.endswith("-export.json"):
            continue
        r = read(p)
        assert r["termination"] == "schedule_end" and len(set(r["facts"])) == len(
            r["facts"]
        )
        groups[r["case"], r["arm"], r["seed"]].append(r)
        rows.append(r)
    assert len(rows) == 174
    with (dest / "runs.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    pairs = []
    for (case, arm, seed), rr in groups.items():
        a1, b = rr
        assert (a1["facts"], a1["state_sha"], a1["paid"], a1["verdicts"]) == (
            b["facts"],
            b["state_sha"],
            b["paid"],
            b["verdicts"],
        )
        r = a1
        if arm=="prior":
            archived=read(a.previous/f"s{seed}/1M-n1000000"/f"meter-stream-{case}-mps-b0.json")
            assert all(r[k]==archived[k] for k in ("state_sha","facts","verdicts","paid"))
        pairs.append(
            {
                "case": case,
                "arm": arm,
                "seed": seed,
                "facts": len(r["facts"]),
                "reference": r["reference"],
                "coverage": r["coverage"],
                "ept": r["ept"],
                "eps": median(x["cold_eps"] for x in rr),
                "min_seconds": min(x["cold_wall"] for x in rr),
                "max_seconds": max(x["cold_wall"] for x in rr),
                "paid": r["paid"],
                "positive_runs": sum(
                    v > 0 for v in r["credited_by_request_run"].values()
                ),
                "ops": r["signed_ops"],
                "after_first_run": sum(
                    v for k, v in r["credited_by_request_run"].items() if int(k) > 1
                ),
                "mark_attempts": r["work"].get("mark_draws", 0),
                "pending": r["work"].get("draft_pending", 0),
                "terminal": r["state_sha"],
            }
        )
    table(dest / "pairs.csv", pairs)
    bins = defaultdict(Counter)
    trials = []
    for f in sorted((a.out / "hints").glob("*.json")):
        for r in read(f):
            trials.append(r)
            for c in r["curve"]:
                k = r["case"], r["arm"], r["prompt"], c["page"]
                bins[k].update(
                    {
                        "reference_ops": r["ops"],
                        "found_ops": c["ops"],
                        "reference_bindings": r["targets"],
                        "found_bindings": c["hits"],
                        "attempts": c["stats"].get("attempts", 0),
                        "issued": c["stats"].get("issued", 0),
                    }
                )
    if len(trials)!=41*3*5*6+12*3*2*6:
        raise ValueError(("missing frozen-state trials",len(trials)))
    with (dest / "frozen-trials.jsonl").open("w") as f:
        for r in trials:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    table(
        dest / "frozen-curves.csv",
        [
            dict(case=c, arm=a, prompt=p, page=b, **v)
            for (c, a, p, b), v in sorted(bins.items())
        ],
    )
    full = [read(p) for p in sorted(a.out.glob("full-*.json"))]
    assert len(full) == 6
    save(dest / "full-data.json", full)
    budget = []
    for p in sorted((a.out / "cost-prefix").glob("s*/*/b0/sum-divisors.json")):
        r = read(p)
        budget.extend(
            dict(arm=r["arm"], seed=r["seed"], **point) for point in r["paid_curve"]
        )
    if len(budget) != 21 * 9:
        raise ValueError(("missing exact paid prefix observations", len(budget)))
    table(dest / "paid-curves.csv", budget)
    fits = []
    for f in sorted(a.out.glob("s*/*/fit.json")):
        wt = f.parent / "weights.pt"
        fits.append(
            {
                "path": str(wt.relative_to(a.out)),
                "sha256": hashlib.sha256(wt.read_bytes()).hexdigest(),
                "loss": read(f),
            }
        )
    save(dest / "fits.json", fits)


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--destination", type=Path, required=True)
    collect(p.parse_args())
