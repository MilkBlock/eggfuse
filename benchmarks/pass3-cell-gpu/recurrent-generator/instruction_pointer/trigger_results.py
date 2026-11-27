"""Summarize matched A/B/C runs; emit every issued Higher and exact fact-set differences."""

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


def write(out, name, rows):
    with (out / f"{name}.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def groups(rows, cols):
    result = defaultdict(list)
    for r in rows:
        result[tuple(r[k] for k in cols)].append(r)
    return result


def avg(out, name, rows, keys, fields):
    write(
        out,
        name,
        [
            dict(zip(keys, k, strict=True))
            | {"n": len(rs)}
            | {f: mean(r[f] for r in rs) for f in fields}
            for k, rs in groups(rows, keys).items()
        ],
    )


def read(p):
    return json.loads(p.read_text())


def summarize(src, out):
    out.mkdir(parents=True, exist_ok=True)
    train = []
    pairs = []
    runs = []
    higher = []
    diff = []
    snap = []
    facts = []
    for seed in (71, 113):
        for mode in ("none", "dirty", "both"):
            train.append(
                {"mode": mode, "seed": seed} | read(src / f"train-{mode}-{seed}.json")
            )
            pairs.extend(
                {"mode": mode, "seed": seed} | r
                for r in read(src / f"pairs-{mode}-{seed}.json")
            )
        assert len({(r["stream"], r["params"], r["examples"]) for r in train[-3:]}) == 1
    write(out, "training", train)
    avg(
        out, "pairs", pairs, ("mode", "tag", "phase", "intervention"), ("p", "template")
    )
    for case in ("controlled", "fact", "loopfact", "sum-divisors"):
        for budget in ("full",) if case == "controlled" else ("slots", "paid", "full"):
            rows = read(src / f"{case}-{budget}.json")
            assert len(rows) == 18
            for (seed, mode), group in groups(rows, ("seed", "mode")).items():
                check, x, y = sorted(group, key=lambda r: r["rep"])
                assert [check["rep"], x["rep"], y["rep"]] == [-1, 0, 1]
                assert all(
                    check[k] == x[k] == y[k]
                    for k in ("facts", "graph", "ops", "stats", "slots", "receipts")
                )
                tag = {"case": case, "budget": budget, "seed": seed, "mode": mode}
                statuses = Counter(r["status"] for r in check["entries"])
                for h in check["higher"]:
                    higher.append(tag | h)
                    statuses.update(step["status"] for step in h["steps"])
                assert sum(statuses.values()) == x["stats"]["paid"]
                credited = sum(r["effective_ops"] > 0 for r in check["entries"]) + sum(
                    step["effective_ops"] > 0
                    for h in check["higher"]
                    for step in h["steps"]
                )
                unknown = set(statuses) - {
                    "accepted",
                    "duplicate",
                    "untriggered_rule",
                    "binding",
                    "guard",
                    "watermark",
                }
                base = next(
                    r
                    for r in rows
                    if r["rep"] == -1 and r["seed"] == seed and r["mode"] == "none"
                )
                a = {json.dumps(f) for f in base["facts"]}
                b = {json.dumps(f) for f in x["facts"]}
                diff.append(
                    tag
                    | {
                        "same": (a == b and x["graph"] == base["graph"]),
                        "gained": len(b - a),
                        "lost": len(a - b),
                        "extra": sorted(b - a),
                        "missing": sorted(a - b),
                    }
                )
                facts.append(tag | {"graph": x["graph"], "facts": x["facts"]})
                runs.append(
                    tag
                    | {
                        k: x[k]
                        for k in (
                            "covered",
                            "reference",
                            "coverage",
                            "ops",
                            "ept",
                            "slots",
                            "calls",
                            "graph",
                        )
                    }
                    | {
                        "paid": x["stats"]["paid"],
                        "neural": x["stats"]["neural_tokens"],
                        "productive": credited,
                        "accepted": statuses["accepted"],
                        "duplicate": statuses["duplicate"],
                        "untriggered": statuses["untriggered_rule"],
                        "binding": statuses["binding"],
                        "guard": statuses["guard"],
                        "watermark": statuses["watermark"],
                        "other": sum(statuses[k] for k in unknown),
                        "higher": len(check["higher"]),
                        "opened": sum(h["accepted"] for h in check["higher"]),
                        "complete": x["stats"]["higher_completed"],
                        "internal": x["stats"].get("internal", 0),
                        "higher_ops": sum(h["effective_ops"] for h in check["higher"]),
                        "eps": mean([x["eps"], y["eps"]]),
                        "forward_s": x["wall"],
                        "reverse_s": y["wall"],
                        "decode": mean([x["decode"], y["decode"]]),
                    }
                )
        if case != "controlled":
            q = read(src / f"snapshots-{case}.json")
            assert q["graph"] == next(
                r["graph"]
                for r in runs
                if r["case"] == case
                and r["budget"] == "full"
                and r["mode"] == "none"
                and r["seed"] == 71
            )
            snap.extend(
                r
                | {
                    "support": "mixed"
                    if 0 < r["active_supported"] < r["supported"]
                    else "all-active"
                    if r["active_supported"]
                    else "all-clean"
                }
                for r in q["rows"]
            )
    write(out, "runs", runs)
    write(out, "higher", higher)
    write(out, "matched", diff)
    write(out, "facts", facts)
    write(out, "snapshots", snap)
    avg(
        out,
        "egg-opportunity",
        snap,
        ("case", "support", "mode", "intervention"),
        ("p_active", "supported", "active_supported"),
    )
    avg(
        out,
        "results",
        runs,
        ("case", "budget", "mode"),
        (
            "covered",
            "coverage",
            "ept",
            "eps",
            "ops",
            "paid",
            "neural",
            "productive",
            "slots",
            "accepted",
            "untriggered",
            "duplicate",
            "binding",
            "guard",
            "watermark",
            "other",
            "higher",
            "opened",
            "complete",
            "internal",
            "higher_ops",
            "decode",
        ),
    )
    windows = []
    for case in ("fact", "loopfact", "sum-divisors"):
        breakdown = read(src / f"windows-{case}.json")
        for (mode, seed), items in groups(breakdown, ("mode", "seed")).items():
            live = next(
                r
                for r in runs
                if (r["case"], r["budget"], r["mode"], r["seed"])
                == (case, "full", mode, seed)
            )
            assert sum(r["count"] for r in items) == live["neural"]
            # This table records only neural entries; a rejected internal request has its own receipt.
            assert (
                sum(r["count"] for r in items if r["status"] == "untriggered_rule")
                <= live["untriggered"]
            )
        windows.extend(breakdown)
    write(out, "windows", windows)
    (out / "manifest.json").write_text(
        json.dumps(
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(src.glob("*"))
                if p.is_file()
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    summarize(*map(Path, sys.argv[1:]))
