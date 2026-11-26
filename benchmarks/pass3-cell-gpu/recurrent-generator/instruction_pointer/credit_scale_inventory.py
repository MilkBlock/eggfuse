"""Offline semantic accounting for the witnessed single-effect relation DAG family."""

import argparse
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from cell_transaction import STATUS
from credit_scale_fit import load_shard
from data_scale_corpus import program
from discovery_score import write_csv


def partition(a):
    out = a.out
    signatures = set()
    states = set()
    named = set()
    calculations = set()
    positives = set()
    contrasts = defaultdict(set)
    by_kind = Counter()
    by_branch = defaultdict(Counter)
    by_idx = defaultdict(set)
    stats = Counter()
    aliases = Counter()
    manifest = []
    nested = []
    recipes = set()
    primitive_templates = 0

    def snapshot_size():
        return {
            "programs": len(by_idx),
            "states": len(states),
            "state_calculations": len(calculations),
            "verified_state_effects": len(positives),
            "named_requests": len(named),
            "neural_tokens": sum(cnt["full_tokens"] for cnt in by_branch.values()),
            "pure_tokens": by_branch[2]["full_tokens"],
            "pure_states": len(pure_states),
            "pure_verified": len(pure_pos),
        }

    pure_states = set()
    pure_pos = set()
    canonical = {}
    with gzip.open(out / "credits.jsonl.gz", "wt", compresslevel=1) as buf:
        for path in sorted((out / "buffer").glob("*.json.gz")):
            sh = load_shard(path)
            idx, b = sh["idx"], sh["branch"]
            d = a.programs / f"{idx:04d}"
            if not d.is_dir():
                d = out / "novel" / "programs" / f"{idx:04d}"
            if idx not in canonical:
                if len(by_idx) in (16, 64, 152):
                    nested.append(snapshot_size())
                src, sig = program(71391 + idx)
                if sig != sh["signature"] or src != (d / "source.egg").read_text():
                    raise ValueError("unrecognized schema for equivalence accounting")
                p = json.loads((d / "program.json").read_text())
                recipes.add(p["entry_schedule"]["recipe_sha256"])
                primitive_templates += len(p["templates"])
                initial = {r["values"][0]["value"] for r in p["initial"]}
                first = {
                    r["values"][0]["value"]
                    for r in p["initial"]
                    if r["table"] == "P000"
                }
                if initial != first:
                    raise ValueError("missing injectivity witness")
                canonical[idx] = len(first)
            signatures.add(sh["signature"])
            by_idx[idx].add(b)
            cnt = by_branch[b]
            cnt["episodes"] += 1
            cnt["assists"] += sum(len(e["assisted"]) for e in sh["events"])
            for metrics in (sh["device"], sh["cost"], sh["ccp"]):
                for name, value in metrics.items():
                    if name in {"largest_edit_batch", "max_outstanding"}:
                        stats[name] = max(stats[name], value)
                    else:
                        stats[name] += value
            live = {}
            g = dict(sh["origins"])
            consumed = Counter()
            for e in sh["events"]:
                for kk, vv in (
                    ("generated", "response"),
                    ("assisted", "assisted_response"),
                ):
                    for c, res in zip(e[kk], e[vv], strict=True):
                        if g.get(res[0], 0):
                            pp = {ref[0] for ref in c[2]}
                            for parent in pp:
                                if parent > 0:
                                    consumed[parent] += g[res[0]] / len(pp)
            for j, e in enumerate(sh["events"]):
                f = e["frame"]
                for ref in f["retired"]:
                    live.pop((ref["token"], ref["op"]))
                for ref, row in f["updates"]:
                    live[ref["token"], ref["op"]] = row
                if not j:
                    hashes = {
                        row["hashes"][0] for row in live.values() if row["table"] == 0
                    }
                    assert len(hashes) == canonical[idx]
                # Rule heads of this generated family each have a unique table and
                # copy the common i64 input. The full finite scalar domain was checked.
                assert all(row["hashes"][0] in hashes for row in live.values())
                sid = (idx, f["run"], e["semantic_state"])
                states.add(sid)
                if b == 2:
                    pure_states.add(sid)
                phys = set()
                observed = set()
                equivalent = defaultdict(set)
                credit = []

                def binding(c, live=live):
                    return tuple(
                        (live[t, o]["table"], live[t, o]["hashes"][0], v)
                        for t, o, v in c[2]
                    )

                def effect(c):
                    xs = {v[1] for v in binding(c)}
                    if len(xs) != 1:
                        raise ValueError("positive lacks native equal-bound operands")
                    return c[0], xs.pop()

                for c, res, value in zip(
                    e["generated"], e["response"], e["signed_gain"], strict=True
                ):
                    key = (c[0], tuple(map(tuple, c[2])))
                    status = STATUS[res[1]]
                    eq = (c[0], binding(c))
                    named.add((idx, *key))
                    calculations.add((sid, eq))
                    out_key = None
                    if value:
                        out_key = effect(c)
                        observed.add(out_key)
                        equivalent[out_key].add(key)
                        positives.add((sid, out_key))
                        if b == 2:
                            pure_pos.add((sid, out_key))
                    repeat = key in phys
                    semantic_duplicate = False
                    if status == "duplicate":
                        target = effect(c)
                        semantic_duplicate = bool(equivalent[target] - {key})
                    contrast_key = (idx, eq)
                    contrasts[contrast_key].add((sid[1:], status, bool(value)))
                    by_kind[status] += 1
                    cnt["full_tokens"] += 1
                    cnt["accepted"] += int(status == "accepted")
                    cnt["physical_repeat"] += repeat
                    cnt["unique_triggered_occurrences"] += int(
                        not repeat and status != "untriggered_rule"
                    )
                    cnt["positive"] += bool(value)
                    cnt["effective_ops"] += value
                    by_kind["semantic_duplicate_distinct_address"] += semantic_duplicate
                    by_kind["tokens_with_credited_consumer"] += bool(consumed[res[0]])
                    by_kind["accepted_unknown_immediate_value"] += int(
                        status == "accepted" and not value
                    )
                    credit.append(
                        [
                            res[0],
                            status,
                            value,
                            repeat,
                            semantic_duplicate,
                            consumed[res[0]],
                            out_key,
                        ]
                    )
                    phys.add(key)
                for c, gain in e["omitted"]:
                    if (c[0], tuple(map(tuple, c[2]))) in phys:
                        raise ValueError(
                            "attempted request recorded as never generated"
                        )
                    k = effect(c)
                    if k in observed:
                        raise ValueError("omitted signature overlaps observed effect")
                    positives.add((sid, k))
                    calculations.add((sid, (c[0], binding(c))))
                    if b == 2:
                        pure_pos.add((sid, k))
                    equivalent[k].add((c[0], tuple(map(tuple, c[2]))))
                aliases["extra_bindings"] += sum(
                    len(v) - 1 for v in equivalent.values()
                )
                cnt["direct_omissions"] += len(e["omitted"])
                cnt["unknown_forks"] += int(not e["stable"])
                cnt["decisions"] += 1
                obj = {
                    "shard": path.name,
                    "event": j,
                    "state": sid,
                    "online": "frame, context",
                    "policy": sh["checkpoint"],
                    "actual": credit,
                    "omission_field": "omitted",
                    "unknown_unprobed": True,
                }
                buf.write(json.dumps(obj, separators=(",", ":")) + "\n")
            manifest.append(
                {
                    "shard": path.name,
                    "program": idx,
                    "signature": sh["signature"],
                    "policy": sh["checkpoint"],
                    "branch": b,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                }
            )
    nested.append(snapshot_size())
    write_csv(out / "nested.csv", nested)
    different = sum(
        len({s for s, _, _ in v}) > 1 and len({(a, p) for _, a, p in v}) > 1
        for v in contrasts.values()
    )
    record = {
        "programs": len(by_idx),
        "recipes": len(recipes),
        "program_scoped_primitive_templates": primitive_templates,
        "structures": len(signatures),
        "independent_states": len(states),
        "state_calculations": len(calculations),
        "verified_state_effects": len(positives),
        "different_named": len(named),
        "pure_states": len(pure_states),
        "pure_state_effects": len(pure_pos),
        "same_binding_different_outcome": different,
        "aliases": aliases,
        "by_branch": by_branch,
        "receipts": by_kind,
        "counters": stats,
        "compressed_shards_bytes": sum(m["bytes"] for m in manifest),
    }
    (out / "inventory.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    write_csv(out / "shards.csv", manifest)
    print(json.dumps({k: v for k, v in record.items() if k != "counters"}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("programs", type=Path)
    partition(p.parse_args())
