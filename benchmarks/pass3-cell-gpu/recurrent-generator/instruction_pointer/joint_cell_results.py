"""Export attributable native and offline measurements without pooling incompatible budgets."""

import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from joint_cell_corpus import read_rows
from joint_cell_probabilities import previous


def read(p):
    return json.loads(p.read_bytes())


def write(p, x):
    p.write_text(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n")


def lines(p, rows):
    with p.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")


def csvfile(p, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with p.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def lifetimes(events):
    tally = Counter()
    by_name = defaultdict(list)
    by_address = {}
    for e in events:
        name = e["tid"], tuple(e["refs"])
        logical = e["tid"], tuple(r[:2] for r in e["refs"])
        prev = by_name[name]
        if e["effective_ops"] > 0:
            if any(
                x["run"] != e["run"]
                and x["status"] in ("accepted", "duplicate")
                and x["effective_ops"] == 0
                for x in prev
            ):
                tally["previous_legal_zero_now_positive"] += 1
            if any(x["run"] != e["run"] and x["effective_ops"] > 0 for x in prev):
                tally["positive_again_after_run"] += 1
            if logical in by_address and by_address[logical] != name:
                tally["new_version_same_addresses_positive"] += 1
        if e["effective_ops"] > 0:
            tally["productive_requests"] += 1
        if e["status"] == "duplicate":
            tally["entry_duplicate"] += 1
        by_address[logical] = name
        prev.append(e)
    return tally


def export(d, out):
    out.mkdir(exist_ok=True, parents=True)
    old = Path("run-recall/prefix-attention")
    native = []
    facts = {}
    man = {}
    historical = [
        json.loads(l) for l in (old / "interventions.jsonl").read_text().splitlines()
    ]
    prob = previous(old / "interventions.jsonl")
    lines(out / "previous-triples.jsonl", prob)
    scores = []
    cohorts = defaultdict(Counter)
    transfer = []
    for p in sorted(d.glob("prob-*.json")):
        prob += read(p)
    for row in prob:
        if len(row["refs"]) == 3:
            s = dict(
                case=row["case"],
                run=row["run"],
                rule=row["rid"],
                refs=json.dumps(row["refs"], separators=(",", ":")),
                arm=row["arm"],
                seed=row["seed"],
            )
            for i, name in enumerate(("recipe", "first", "second", "third")):
                s[f"p_{name}_before"] = math.exp(row["before"][i])
                s[f"p_{name}_after"] = math.exp(row["after"][i])
                s[f"dlog_{name}"] = row["delta"][i]
            scores.append(
                s
                | {
                    k: row[k]
                    for k in ("log_before", "log_after", "log_change", "largest_loss")
                }
            )
    csvfile(out / "triple-targets.csv", scores)
    diagnostic = [
        r for r in historical if r["arm"] in ("base", "sparse") and r["seed"] == 0
    ]
    for p in sorted(d.glob("audit-*.json")):
        diagnostic += read(p)
    detail = []
    for r in diagnostic:
        path = (
            "historical_index"
            if r["arm"] == "sparse" and r["index"]
            else "historical_fallback"
            if r["arm"] == "sparse"
            else r["arm"]
        )
        key = (r["arity"], r["forced"], path, r["seed"])
        cnt = cohorts[key]
        cnt.update(
            {
                k: r[k]
                for k in (
                    "paid",
                    "productive",
                    "ops",
                    "accepted",
                    "binding",
                    "duplicates",
                    "guard",
                    "other_rejects",
                )
            }
        )
        detail.append({k: v for k, v in r.items() if k != "probabilities"})
    lines(out / "correct-recipe.jsonl", detail)
    csvfile(
        out / "correct-recipe.csv",
        [
            dict(arity=k[0], forced=k[1], arm=k[2], seed=k[3], **cnt)
            for k, cnt in sorted(cohorts.items())
        ],
    )
    aliases = [r for p in sorted(d.glob("aliases-*.json")) for r in read(p)]
    write(out / "aliases.json", aliases)
    free_rules = []
    for p in sorted([*d.glob("live-*.json"), *d.glob("timing*.json")]):
        x = read(p)
        events = read_rows(p.with_suffix(".pkl.gz"))
        if x["arm"] == "sweep" and x["budget"] == "full" and p.stem.startswith("live-"):
            case = x["case"]
            trained = set(read(d / f"{case}-inventory.json")["signatures"])
            rules = read(d / f"rule-signatures-{case}.json")
            by = defaultdict(Counter)
            for r in events:
                phase = (
                    "Higher"
                    if r["tid"] != r["rid"]
                    else "seen_rule"
                    if rules[str(r["rid"])] in trained
                    else "unseen_rule"
                )
                by[phase].update(
                    signed=1,
                    productive=int(r["effective_ops"] > 0),
                    effective_ops=r["effective_ops"],
                )
            free_rules.extend(
                dict(case=case, seed=x["seed"], draw=x["draw"], group=k, **v)
                for k, v in by.items()
            )
        extra = lifetimes(events)
        assert len(events) == x["stats"]["neural_tokens"]
        facts[p.stem] = x["facts"]
        native.append(
            dict(
                trial=p.stem,
                **{
                    k: x[k]
                    for k in (
                        "case",
                        "arm",
                        "budget",
                        "seed",
                        "draw",
                        "coverage",
                        "ept",
                        "eps",
                        "covered",
                        "reference",
                        "ops",
                        "wall",
                        "decode_s",
                        "pending",
                        "graph",
                    )
                },
                paid=x["stats"]["paid"],
                higher=x["stats"].get("higher_selected", 0),
                higher_completed=x["stats"].get("higher_completed", 0),
                neural_tokens=len(events),
                offered=x["decoder"]["offered"],
                accepted=x["receipts"]["accepted"],
                **x["receipts"]["rejected"],
                **extra,
                **x["duplicates"],
            )
        )
    csvfile(out / "generalization-free.csv", free_rules)
    csvfile(out / "native.csv", native)
    write(out / "facts.json", facts)
    grouped = defaultdict(list)
    for r in native:
        if r["trial"].startswith("live-"):
            grouped[r["case"], r["budget"], r["arm"]].append(r)
    compact = []
    for (case, budget, arm), runs in sorted(grouped.items()):
        rec = dict(case=case, budget=budget, arm=arm, n=len(runs))
        for col in ("covered", "coverage", "paid", "ops", "ept", "eps"):
            values = [r[col] for r in runs]
            rec[col + "_median"] = median(values)
            rec[col + "_min"] = min(values)
            rec[col + "_max"] = max(values)
        compact.append(rec)
    csvfile(out / "native-summary.csv", compact)
    timing = [r for r in native if r["trial"].startswith("timing")]
    for r in timing:
        k = r["trial"].split("-", 1)[1]
        base = next(v for v in native if v["trial"] == "live-" + k)
        assert (
            all(r[i] == base[i] for i in ("paid", "graph", "ops", "covered"))
            and facts[r["trial"]] == facts["live-" + k]
        )
    summaries = {}
    for case in ("fact", "loopfact", "sum-divisors"):
        a = read(d / f"{case}-inventory.json")
        summaries[case] = {k: v for k, v in a.items() if k != "signatures"}
    write(
        out / "training.json",
        dict(
            inventory=summaries,
            archive=read(d / "legacy.json"),
            training={
                p.stem: read(p)
                for p in d.glob("*.json")
                if p.stem.rsplit("-", 1)[-1] in ("71", "113")
                and (p.stem.startswith(("fact-", "loopfact-", "sum-divisors-")))
            },
            native_replay={p.stem: read(p) for p in d.glob("corpus-*.json")},
        ),
    )
    lines(out / "generalization.jsonl", read(d / "generalization.json"))
    lines(out / "future-probes.jsonl", read(d / "future-probes.json"))
    lines(out / "response-probe.jsonl", read(d / "response-probe.json"))
    write(out / "root-competition.json", read(d / "root-competition.json"))
    x = read(d / "new-higher.json")
    seen = set(read(d / "fact-inventory.json")["signatures"])
    for r in x:
        assert not seen.intersection(r["signatures"])
        transfer.append(
            dict(
                arm=r["arm"],
                arity=r["arity"],
                seed=r["seed"],
                draw=r["draw"],
                selected=len(r["higher"]),
                accepted=sum(q["accepted"] for q in r["higher"]),
                completed=sum(q["completed"] for q in r["higher"]),
                completed_productive=sum(
                    q["completed"] and q["effective_ops"] > 0 for q in r["higher"]
                ),
                graph=r["metrics"]["graph"],
                **{k: r["metrics"][k] for k in ("coverage", "ept", "eps", "ops")},
            )
        )
    csvfile(out / "new-higher.csv", transfer)
    for p in sorted(d.iterdir()):
        if p.is_file() and (
            p.suffix == ".pt"
            or p.suffixes[-2:] == [".pkl", ".gz"]
            or p.name == "new-higher.json"
        ):
            with p.open("rb") as f:
                man[p.name] = dict(
                    bytes=p.stat().st_size,
                    sha256=hashlib.file_digest(f, "sha256").hexdigest(),
                )
    for p in [
        d.parent / "rule-publication/both-71.pt",
        *sorted(d.glob("legacy-*/rows.pkl.gz")),
    ]:
        with p.open("rb") as f:
            rel = (
                "../rule-publication/both-71.pt"
                if p.parent != d and p.name == "both-71.pt"
                else str(p.relative_to(d))
            )
            man[rel] = dict(
                bytes=p.stat().st_size,
                sha256=hashlib.file_digest(f, "sha256").hexdigest(),
            )
    write(out / "manifest.json", man)


if __name__ == "__main__":
    export(Path(sys.argv[1]), Path(sys.argv[2]))
