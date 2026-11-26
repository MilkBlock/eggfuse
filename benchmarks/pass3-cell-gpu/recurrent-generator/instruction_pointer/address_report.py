"""Summarize the complete witness ledger and distinguish capacity, sampling and model loss."""

import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from draft_results import csvfile
from parallel_budget import args


def load(p):
    return json.loads(p.read_bytes())


def expectation(ps, n=256):
    return sum(1 - (1 - min(1, max(0, p))) ** n for p in ps)


def write(dest, name, rows):
    csvfile(dest / (name + ".csv"), rows)


def report(a):
    dest = a.dest
    dest.mkdir(exist_ok=True, parents=True)
    out = a.out
    result = []
    layers = []
    stages = []
    case_summary = []
    manifest = []
    for f in sorted(out.glob("paths-*.jsonl.gz")):
        arm = f.name[6:-9]
        groups = defaultdict(list)
        with gzip.open(f, "rt") as src:
            for line in src:
                rec = json.loads(line)
                groups[rec["case"], rec["run"]].append(rec)
        slots = defaultdict(list)
        bydepth = defaultdict(list)
        for (case, run), records in groups.items():
            roots = Counter(r["rule"] for r in records)
            parents = Counter((r["rule"], str(r["refs"][:1])) for r in records)
            probs = []
            template = {}
            first = {}
            two = {}
            force_rule = []
            force_first = []
            for r in records:
                ss = r["steps"]
                v = [s["p"] for s in ss]
                rid = r["rule"]
                ref = str(r["refs"][:1])
                template[rid] = v[0]
                first[rid, ref] = float(np.prod(v[:2]))
                two[rid, str(r["refs"][:2])] = float(np.prod(v[:3]))
                probs.append(r["prob"])
                force_rule.append(roots[rid] / len(records) * np.prod(v[1:]))
                force_first.append(parents[rid, ref] / len(records) * np.prod(v[2:]))
                for idx, s in enumerate(ss):
                    role = (
                        "template"
                        if not idx
                        else "first_parent"
                        if idx == 1
                        else "later_parent"
                    )
                    slots[role].append(s)
                    for depth, p in enumerate(s.get("path", ()), 1):
                        bydepth[role, depth].append(p)
            mass = sum(probs)
            M = len(probs)
            result.append(
                {
                    "method": arm,
                    "case": case,
                    "run": run,
                    "known": M,
                    "oracle": min(M, 256),
                    "template_mass": sum(template.values()),
                    "first_mass": sum(first.values()),
                    "second_mass": sum(two.values()),
                    "complete_mass": mass,
                    "ideal_iid": expectation([1 / M] * M),
                    "uniform_at_actual_mass": expectation([mass / M] * M),
                    "expected": expectation(probs),
                    "force_template": expectation(force_rule),
                    "force_template_first": expectation(force_first),
                    "median_complete_p": float(np.median(probs)),
                }
            )
        for role, ss in slots.items():
            rank = np.array([s["rank"] or np.inf for s in ss])
            pp = np.array([s["p"] for s in ss])
            stages.append(
                {
                    "method": arm,
                    "role": role,
                    "n": len(ss),
                    "outside": sum(not s["in_domain"] for s in ss),
                    "p_mean": pp.mean(),
                    "p_median": np.median(pp),
                    "rank_median": np.median(rank),
                    "rank1": (rank == 1).mean(),
                    "rank8": (rank <= 8).mean(),
                    "strict_unique_first": np.mean(
                        [s.get("rank") == 1 and s.get("ties") == 1 for s in ss]
                    ),
                    "ties_median": np.median([s["ties"] for s in ss if s["in_domain"]]),
                }
            )
        for (role, depth), v in bydepth.items():
            layers.append(
                {
                    "method": arm,
                    "role": role,
                    "depth": depth,
                    "n": len(v),
                    "mean": np.mean(v),
                    "median": np.median(v),
                    "greedy_accuracy": np.mean(np.array(v) >= 0.5),
                }
            )
        manifest.append(
            {
                "file": f.name,
                "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                "marks": sum(map(len, groups.values())),
            }
        )
    for f in sorted(out.glob("sample-*.json")):
        case_summary.extend(load(f))
    native = []
    for f in sorted(out.glob("native-address/*/*/run.json")):
        x = load(f)
        s = Counter(x["work"])
        g = Counter(x["device"])
        native.append(
            {
                "case": x["case"],
                "arm": x["method"],
                "block": x["block"],
                "cap": x["cap"],
                "pages": x["pages"],
                "covered": x["covered"],
                "reference": x["reference"],
                "graph": x["state_sha"],
                "facts_sha": hashlib.sha256(
                    json.dumps(x["facts"]).encode()
                ).hexdigest(),
                "paid": x["paid"],
                "effective": x["signed_ops"],
                "ept": x["ept"],
                "eps": x["cold_eps"],
                "wall": x["cold_wall"],
                "termination": x["termination"],
                "scores": s["address_forward_calls"],
                "domain_reads": s["device_pivot_visits"],
                "template_reads": s["template_reads"],
                "projections": s["owner_projection_reads"],
                "readbacks": g["boundary_readbacks"],
                "reindexed": g["semantic_keys_reindexed"],
                "semantic_bytes": g["semantic_cached_bytes"],
                "index_updates": g["index_row_updates"],
                "ccp_sync": x["synchronizations"],
                "draws": s["mark_draws"],
                "duplicates": s["same_run_repeat_signed"],
                "native_duplicate": x["verdicts"].get("duplicate", 0),
            }
        )
    for row in case_summary:
        # Resolved below from native recall on the identical draws.
        row["semantic_primitive"] = 0
        row["only_higher_root"] = 0
    idx = {(x["case"], x["arm"], x["run"], x["n"]): x for x in case_summary}
    for fp in out.glob("sample-*.json"):
        sample = load(fp)[0]
        for v in load(out / f"semantic-{fp.name}"):
            row = idx[sample["case"], sample["arm"], v["run"], v["n"]]
            row["semantic_primitive"] = v["semantic"]
            row["only_higher_root"] = v["higher_entry_only"]
    for name, rows in (
        ("witnesses", result),
        ("stages", stages),
        ("layers", layers),
        ("samples", case_summary),
        ("native", native),
        ("path-manifest", manifest),
    ):
        write(dest, name, rows)
    k = a.previous_trial / "native/sum-divisors/flow-256-1-p2-b0"
    x = load(k / "run.json")
    receipts = load(k / "receipts.json")
    reasons = [
        {
            "run": r,
            "request": req,
            "draft_uid": uid,
            "rule": rule,
            "higher": h,
            "status": status,
        }
        for r, req, uid, rule, status, h in receipts
        if status == 2
    ]
    assert len(reasons) == x["verdicts"]["untriggered_rule"] == 3917
    write(dest, "untriggered", reasons)
    write(dest, "growth", load(out / "growth.json"))
    write(dest, "substitutions", load(out / "substitutions.json"))
    write(dest, "original-native-recall", load(out / "original-native-recall.json"))
    for name in ("alias.csv", "paths-original.jsonl.gz"):
        (dest / name).write_bytes((out / name).read_bytes())
    weights = {
        f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in out.glob("*.pt")
    }
    (dest / "checkpoints.json").write_text(json.dumps(weights, indent=2) + "\n")
    for name in ("semantic", "worked-example"):
        (dest / (name + ".json")).write_bytes((out / (name + ".json")).read_bytes())
    old = load(a.previous_trial / "audit-draws.json")
    new = load(out / "audit-draws.json")
    assert old == new and sum(r["hits"] for r in new if r["budget"] == 256) == 159
    write(
        dest,
        "reproduced-draws",
        [
            {
                "case": r["case"],
                "run": r["run"],
                "budget": r["budget"],
                "hits": r["hits"],
                "oracle": r["oracle"],
                "repeat": r.get("repeat", 0),
                "incomplete": r.get("incomplete", 0),
                "outside_witness_template": r.get("wrong_template", 0),
            }
            for r in new
        ],
    )
    for f in out.glob("loss-*.json"):
        (dest / f.name).write_bytes(f.read_bytes())
    if (out / "train-loss.json").exists():
        (dest / "train-loss.json").write_bytes((out / "train-loss.json").read_bytes())


if __name__ == "__main__":
    p = args()
    p.add_argument("--dest", type=Path, required=True)
    p.add_argument("--previous-trial", type=Path, required=True)
    report(p.parse_args())
