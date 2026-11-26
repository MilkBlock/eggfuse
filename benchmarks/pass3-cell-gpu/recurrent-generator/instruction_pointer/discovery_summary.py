"""Aggregate paired counterfactuals; seeds repeat the same states and must not inflate their count."""

import csv
import gzip
import math
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

from discovery_score import write_csv
from discovery_states import cli, read


def tab(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def ratios(c):
    def rate(num, den):
        return c[num] / c[den] if c[den] else None

    return dict(
        template_mass=rate("template_ok", "n"),
        first_mass=rate("first_ok", "first_den"),
        later_mass=rate("later_ok", "later_den"),
        complete_mass=rate("productive_draws", "n"),
        physical_repeat_rate=rate("physical_repeat", "n"),
        semantic_repeat_rate=rate("semantic_duplicates", "n"),
        acceptance=rate("actual_full_accepted", "n")
        if c["budget"] == 256
        else rate("distinct", "n"),
    )


def summary(a):
    dest = a.dest
    dest.mkdir(exist_ok=True, parents=True)
    frozen = []
    native = []
    stalls = []
    dirty = []
    for case in a.cases:
        events = read(a.out / "dirty" / case / "admissions.json")
        cf = Counter()
        for r, _, rid, origin, flag, v in events:
            src = (
                "continuation"
                if origin is None
                else "same_run"
                if r == origin[0]
                else "cross_run"
            )
            cf[
                src,
                v,
                "unobserved" if origin is None else "dirty" if origin[1] else "clean",
                flag,
            ] += 1
        dirty.extend(
            dict(
                case=case,
                source=s,
                verdict=v,
                generated_dirty=g,
                admission_dirty=k,
                count=n,
            )
            for (s, v, g, k), n in cf.items()
        )
        for source in ("teacher", "rollout"):
            path = a.out / source / case
            frozen += tab(path / "measured.csv")
            stalls.extend(
                dict(case=case, **v) for v in read(path / "states.json") if v["stall"]
            )
        for f in sorted(a.out.glob(f"**/native-address/{case}/*/run.json")):
            if "paired" in f.relative_to(a.out).parts:
                continue
            z = read(f)
            seed = (
                536
                if "seeds" not in f.parts
                else int(f.parts[f.parts.index("seeds") + 1])
            )
            native.append(
                dict(
                    case=case,
                    arm=z["method"],
                    seed=seed,
                    block=z["block"],
                    facts=z["covered"],
                    reference=z["reference"],
                    graph=z["state_sha"],
                    paid=z["paid"],
                    ops=z["signed_ops"],
                    EPT=z["ept"],
                    EPS=z["cold_eps"],
                    wall=z["cold_wall"],
                    shortfall=z["device"].get("complete_shortfall", 0),
                    pivot_reads=z["work"].get("device_pivot_visits", 0),
                    random_indexed=z["device"].get("random_indexed_rows", 0),
                )
            )
    write_csv(dest / "native.csv", native)
    write_csv(dest / "dirty.csv", dirty)
    write_csv(dest / "stalls.csv", stalls)
    agg = defaultdict(Counter)
    groups = ("case", "source", "arm", "seed", "budget")
    for row in frozen:
        case, source, arm, seed, budget = (row[k] for k in groups)
        nums = {
            k: int(v)
            for k, v in row.items()
            if k not in groups and v and k not in ("domain", "run")
        }
        for name in (case, "all"):
            key = (name, source, arm, seed, budget)
            agg[key].update(nums)
            agg[key]["states"] += 1
    totals = []
    for key, c in agg.items():
        c["budget"] = int(key[-1])
        totals.append(dict(**dict(zip(groups[:-1], key[:-1])), **c, **ratios(c)))
    write_csv(dest / "seed-curves.csv", totals)
    means = []
    for src in ("teacher", "rollout"):
        for arm in ("uniform", "unique", "factored", "A", "D", "oracle"):
            for k in (4, 16, 64, 256):
                g = [
                    x
                    for x in totals
                    if x["case"] == "all"
                    and x["source"] == src
                    and x["arm"] == arm
                    and x["budget"] == k
                ]
                keys = (
                    "n",
                    "productive",
                    "distinct",
                    "template_mass",
                    "first_mass",
                    "later_mass",
                    "complete_mass",
                    "physical_repeat_rate",
                    "semantic_repeat_rate",
                    "acceptance",
                    "actual_full_ops",
                    "actual_full_productive",
                )
                means.append(
                    dict(
                        source=src,
                        arm=arm,
                        budget=k,
                        **{
                            field: mean(x.get(field, 0) or 0 for x in g)
                            for field in keys
                        },
                        productive_min=min(x.get("productive", 0) for x in g),
                        productive_max=max(x.get("productive", 0) for x in g),
                    )
                )
    write_csv(dest / "curves.csv", means)
    roll = []
    for case in a.cases:
        for arm in ("uniform", "unique", "factored", "A", "D"):
            g = [x for x in native if x["case"] == case and x["arm"] == arm]
            by_seed = defaultdict(list)
            for x in g:
                by_seed[x["seed"]].append(x)
            assert len(by_seed) == 5 and len(by_seed[536]) == 2
            for pair in by_seed.values():
                assert len({x["graph"] for x in pair}) == 1
            roll.append(
                dict(
                    case=case,
                    arm=arm,
                    reference=g[0]["reference"],
                    **{
                        k: mean(median(x[k] for x in pair) for pair in by_seed.values())
                        for k in ("facts", "paid", "ops", "EPT", "EPS")
                    },
                    min_facts=min(x["facts"] for x in g),
                    max_facts=max(x["facts"] for x in g),
                )
            )
    timing = []
    for x in roll:
        case, arm = x["case"], x["arm"]
        paths = sorted(
            (a.out / "paired/native-address" / case).glob(f"{arm}-k16-p2-b*/run.json")
        )
        pair = [read(f) for f in paths]
        original = next(
            r
            for r in native
            if r["case"] == case and r["arm"] == arm and r["seed"] == 536
        )
        assert len(pair) == 2 and all(
            z["state_sha"] == original["graph"] and z["paid"] == original["paid"]
            for z in pair
        )
        x["paired_EPS_536"] = median(z["cold_eps"] for z in pair)
        timing.extend(
            dict(
                case=case,
                arm=arm,
                block=z["block"],
                seconds=z["cold_wall"],
                EPS=z["cold_eps"],
                graph=z["state_sha"],
            )
            for z in pair
        )
    write_csv(dest / "timing.csv", timing)
    write_csv(dest / "independent.csv", roll)
    loss = []
    for arm in "ABCD":
        sets = defaultdict(list)
        with gzip.open(a.contract / f"prob-{arm}.csv.gz", "rt") as f:
            for x in csv.DictReader(f):
                sets[x["case"], x["run"]].append(x)
        for (case, run), xs in sets.items():
            productive = [x for x in xs if int(x["gain"]) > 0]
            ps = [float(x["p_class"]) for x in productive]
            loss.append(
                dict(
                    arm=arm,
                    case=case,
                    run=run,
                    known=len(xs),
                    useful=len(ps),
                    canonical=sum(float(x["p_exact"]) for x in productive),
                    useful_mass=sum(ps),
                    signed_mass=sum(float(x["p_class"]) for x in xs),
                    expected_distinct_256=sum(
                        -math.expm1(256 * math.log1p(-v)) if v < 1 else 1 for v in ps
                    ),
                )
            )
    write_csv(dest / "loss.csv", loss)
    shutil.copyfile(a.out / "semantic.json", dest / "semantic.json")


if __name__ == "__main__":
    p = cli()
    p.add_argument("--dest", type=Path, required=True)
    summary(p.parse_args())
