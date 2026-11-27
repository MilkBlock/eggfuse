"""Export complete native accounting, matched facts and held-out convergence curves."""

import hashlib
import json
import shutil
import sys
from pathlib import Path
from statistics import mean

from competition_results import groups, table


def summary(folder, name, rows, keys, fields):
    result = []
    for k, group in sorted(groups(rows, keys).items()):
        result.append(
            {
                **dict(zip(keys, k)),
                "runs": len(group),
                **{f: mean(r[f] for r in group) for f in fields},
            }
        )
    table(folder, name, result)


def export(src, dest):
    dest.mkdir(exist_ok=True, parents=True)
    egg = []
    traces = []
    forks = []
    comparisons = []
    native = []
    for p in sorted(src.glob("egg-*.json")):
        records = json.loads(p.read_text())
        for pair in groups(records, ("mode", "seed", "case", "cap")).values():
            a, b = sorted(pair, key=lambda r: r["rep"])
            assert [a["rep"], b["rep"]] == [0, 1]
            assert all(
                a[k] == b[k]
                for k in ("graph", "counts", "receipts", "facts", "pages", "ops")
            )
            counts = a["counts"]
            assert counts["offered"] == sum(
                counts.get(k, 0)
                for k in (
                    "no_menu",
                    "signed",
                    "empty_parent",
                    "no_typed_token",
                    "exhausted_page",
                )
            )
            statuses = a["receipts"]
            rejected = statuses["rejected"]
            row = {
                k: a[k]
                for k in (
                    "case",
                    "mode",
                    "cap",
                    "seed",
                    "covered",
                    "reference",
                    "coverage",
                    "graph",
                    "ops",
                    "ept",
                )
            }
            row.update(
                slot_limit=a.get("slot_limit") or 0,
                draw=a.get("draw", 193),
                paid=a["stats"]["paid"],
                accepted=statuses["accepted"],
                dup=statuses["duplicates"],
                untriggered=rejected.get("untriggered_rule", 0),
                binding=rejected.get("binding", 0),
                other_reject=sum(rejected.values())
                - rejected.get("untriggered_rule", 0)
                - rejected.get("binding", 0),
                eps=mean(r["eps"] for r in pair),
                wall=mean(r["wall"] for r in pair),
                wall1=a["wall"],
                wall2=b["wall"],
                decode=mean(r["decode_s"] for r in pair),
                prepare=mean(r["prepare_s"] for r in pair),
                offered=counts["offered"],
                attempted=counts["attempted"],
                empty=counts["empty_parent"],
                no_typed=counts.get("no_typed_token", 0),
                exhausted=counts.get("exhausted_page", 0),
                reads=counts["distribution_reads"],
                nomenu=counts.get("no_menu", 0),
            )
            assert row["paid"] == sum(
                row[k]
                for k in ("accepted", "dup", "untriggered", "binding", "other_reject")
            )
            egg.append(row)
            native.append((row, a))
            byrun = {}
            for run, tokens in a["pages"]:
                byrun.setdefault(run, []).extend(tokens)
            for run in (1, 2, 3):
                ts = byrun.get(run, [])
                traces.append(
                    {
                        **{
                            k: row[k]
                            for k in (
                                "case",
                                "mode",
                                "cap",
                                "slot_limit",
                                "seed",
                                "draw",
                            )
                        },
                        "run": run,
                        "signed": len(ts),
                        "accepted": sum(t[2] == "accepted" for t in ts),
                        "tokens": json.dumps(ts, separators=(",", ":")),
                    }
                )
    for case in ("fact", "loopfact", "sum-divisors"):
        for seed in (71, 113):
            for cap, slot, draw, modes in [
                (0, 0, 193, "A B C TB TC"),
                (96, 0, 193, "A B C TB TC"),
                (32, 0, 193, "A B C"),
                (96, 0, 827, "A B C"),
                (0, 96, 193, "A B C"),
                (0, 384, 193, "A B C"),
            ]:
                z = {
                    r["mode"]: a
                    for r, a in native
                    if (r["case"], r["seed"], r["cap"], r["slot_limit"], r["draw"])
                    == (case, seed, cap, slot, draw)
                }
                if set(z) != set(modes.split()):
                    raise ValueError((case, seed, cap, draw, z.keys()))
                for x, y in (("A", "B"), ("B", "C"), ("B", "TB"), ("C", "TC")):
                    if y in z:
                        l, r = set(z[x]["facts"]), set(z[y]["facts"])
                        comparisons.append(
                            {
                                "case": case,
                                "seed": seed,
                                "cap": cap,
                                "slot_limit": slot,
                                "draw": draw,
                                "base": x,
                                "changed": y,
                                "same_graph": z[x]["graph"] == z[y]["graph"],
                                "common": len(l & r),
                                "gained": sorted(r - l),
                                "lost": sorted(l - r),
                            }
                        )
        f = src / f"fork-{case}.json"
        shutil.copyfile(f, dest / f.name)
        for r in json.loads(f.read_text()):
            forks.append(
                {k: v for k, v in r.items() if k != "probes"}
                | {
                    "confirmed_positive_mass": sum(
                        t["p"] for t in r["probes"] if t["new"]
                    ),
                    "probed": len(r["probes"]),
                }
            )
    table(dest, "native", egg)
    table(dest, "windows", traces)
    table(dest, "matched", comparisons)
    table(dest, "forks", forks)
    summary(
        dest,
        "egg",
        egg,
        ("case", "cap", "slot_limit", "draw", "mode"),
        (
            "coverage",
            "covered",
            "paid",
            "ept",
            "eps",
            "wall",
            "decode",
            "prepare",
            "offered",
            "attempted",
            "empty",
            "no_typed",
            "exhausted",
            "reads",
            "accepted",
            "dup",
            "untriggered",
            "binding",
            "other_reject",
        ),
    )
    shutil.copyfile(src / "higher.csv", dest / "higher.csv")
    rows = []
    for cat in ("primitive", "short", "medium", "multi"):
        for seed in (71, 113):
            rr = json.loads((src / f"scale-{cat}-{seed}.json").read_text())
            assert len(rr) == 32
            for r in rr:
                rows.append(
                    {
                        k: r[k]
                        for k in (
                            "cat",
                            "seed",
                            "index",
                            "draw",
                            "step",
                            "exposures",
                            "ce",
                            "train_s",
                            "coverage",
                            "covered",
                            "reference",
                            "graph",
                            "decisions",
                            "calls",
                            "wall",
                            "read_s",
                            "ops",
                            "ept",
                            "eps",
                            "lengths",
                        )
                    }
                    | {
                        "paid": r["stats"]["paid"],
                        "completed": r["stats"]["higher_completed"],
                        "internal": r["stats"].get("internal", 0),
                    }
                )
    table(dest, "scale-native", rows)
    matches = []
    for key, points in groups(rows, ("step", "index", "seed", "draw")).items():
        lookup = {r["cat"]: r for r in points}
        base = lookup["primitive"]
        for cat in ("short", "medium", "multi"):
            row = lookup[cat]
            matches.append(
                {
                    "step": key[0],
                    "index": key[1],
                    "seed": key[2],
                    "draw": key[3],
                    "cat": cat,
                    "same_graph": base["graph"] == row["graph"],
                    "covered_delta": row["covered"] - base["covered"],
                    "decision_delta": row["decisions"] - base["decisions"],
                    "paid_delta": row["paid"] - base["paid"],
                    "wall_ratio": row["wall"] / base["wall"],
                }
            )
    table(dest, "scale-matched", matches)
    summary(
        dest,
        "scale",
        rows,
        ("cat", "step"),
        (
            "exposures",
            "ce",
            "train_s",
            "coverage",
            "decisions",
            "calls",
            "paid",
            "ops",
            "completed",
            "internal",
            "ept",
            "eps",
            "read_s",
            "wall",
        ),
    )
    timed = json.loads((src / "abstraction-timing.json").read_text())
    if len(timed) != 256:
        raise ValueError("incomplete four-order scaling trial")
    timed_out = []
    for key, pts in groups(timed, ("seed", "index", "draw", "rep")).items():
        base = next(r for r in pts if r["cat"] == "primitive")
        for r in pts:
            expected = next(
                z
                for z in rows
                if z["cat"] == r["cat"]
                and z["step"] == 192
                and (z["seed"], z["index"], z["draw"]) == key[:3]
            )
            assert (
                r["graph"] == expected["graph"]
                and r["ops"] == expected["ops"]
                and r["decisions"] == expected["decisions"]
            )
            timed_out.append(
                {
                    k: r[k]
                    for k in (
                        "cat",
                        "seed",
                        "index",
                        "draw",
                        "rep",
                        "wall",
                        "decisions",
                        "ops",
                        "coverage",
                        "ept",
                        "eps",
                    )
                }
                | {
                    "same": r["graph"] == base["graph"] and r["facts"] == base["facts"],
                    "wall_ratio": r["wall"] / base["wall"],
                }
            )
    table(dest, "scale-timing", timed_out)
    training = []
    provenance = {}
    for seed in (71, 113):
        for tag, folder in (
            ("visible", src.parent / "response-memory"),
            ("structured", src),
        ):
            for step, loss, n in json.loads(
                (folder / f"curve-{tag}-{seed}.json").read_text()
            ):
                training.append(
                    {
                        "mode": tag,
                        "seed": seed,
                        "step": step,
                        "batch_ce": loss,
                        "target_exposures": n,
                    }
                )
        for path in (
            src.parent / "state-transition" / f"transition-{seed}.pt",
            src.parent / "response-memory" / f"visible-{seed}.pt",
        ):
            provenance[str(path.relative_to(src.parent))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    table(dest, "training", training)
    (dest / "inputs.json").write_text(json.dumps(provenance, indent=2) + "\n")
    (dest / "artifacts.json").write_text(
        json.dumps(
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(src.iterdir())
                if p.is_file()
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    export(*map(Path, sys.argv[1:]))
