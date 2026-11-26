"""Offline alignment of complete tokens, publication states and native evidence."""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from cell_transaction import STATUS
from credit_scale_fit import load_shard
from discovery_score import token


def schema(ir):
    tables = {x["name"]: i for i, x in enumerate(ir["recipe"]["tables"])}
    single = {}
    for rid, r in enumerate(ir["recipe"]["rules"]):
        ops = r["effects"]
        if (
            len(ops) != 1
            or ops[0].get("kind") != "construct"
            or len(ops[0]["args"]) != 1
        ):
            continue
        out = ops[0]["call"].get("table", "")
        if not re.fullmatch(r"P\d+|Memo", out):
            continue
        arg = ops[0]["args"][0]
        for n, q in enumerate(t for t in r["query"] if "table" in t["call"]):
            if q["args"][0] == arg:
                single[rid] = (tables[out], n)
                break
    return single


def decode(sh, single):
    live = {}
    for event, sched in zip(sh["events"], sh["scheduler"]):
        f = event["frame"]
        assert f["run"] == sched[0] and len(event["generated"]) == len(
            event["response"]
        )
        for q in f["retired"]:
            live.pop((q["token"], q["op"]), None)
        for q, row in f["updates"]:
            live[q["token"], q["op"]] = row
        present = {
            (row["table"], row["hashes"][0])
            for row in live.values()
            if row["hashes"] and not row["forwarded"]
        }

        def signature(c):
            if c.rule not in single:
                return None
            t, idx = single[c.rule]
            owner, op, version = c.refs[idx]
            row = live.get((owner, op))
            if row and row["version"] == version and row["hashes"]:
                return t, row["hashes"][0]
            return None

        examples = []
        for row, res, gain in zip(
            event["generated"], event["response"], event["signed_gain"], strict=True
        ):
            c = token(row)
            sig = signature(c)
            status = STATUS[res[1]]
            # Native acceptance with zero marginal gain plus the idempotent Recipe and
            # an already published identical output certify semantic duplication.
            seen = (
                gain == 0
                and status == "accepted"
                and sig is not None
                and sig in present
            )
            examples.append((c, status, gain, sig, seen))
        omitted = [
            (token(row), gain, signature(token(row))) for row, gain in event["omitted"]
        ]
        yield examples, omitted


def comparable(cell, left, right):
    # Odd negative owners are initial. Even negative owners are native repair receipts.
    return left != right and (
        left[0] == right[0] or all(t < 0 and t % 2 for t, _, _ in cell.refs)
    )


def reduce_data(program_shards, single, limits, seed):
    rng = np.random.default_rng(seed)
    records = {}
    decoded = {b: list(decode(sh, single)) for b, sh in program_shards.items()}
    witnesses = defaultdict(lambda: [[], []])
    for b, runs in decoded.items():
        offset = 0
        for j, (items, _) in enumerate(runs):
            for i, (c, status, g, sig, done) in enumerate(items):
                if g or done:
                    witnesses[c][int(done)].append((b, j, offset + i))
            offset += len(items)
    reserve = defaultdict(set)
    for c, (high, low) in witnesses.items():
        pair = next(
            ((a, b) for a in high for b in low if comparable(c, a[:2], b[:2])), None
        )
        if pair:
            for branch, j, index in pair:
                reserve[branch].add(index)
    for branch, runs in decoded.items():
        counts = [sum(len(x[k]) for x in runs) for k in (0, 1)]
        selections = [
            set(rng.choice(count, size=min(count, limit), replace=False).tolist())
            for count, limit in zip(counts, limits[branch], strict=True)
        ]
        forced = sorted(reserve[branch])[: limits[branch][0] // 4]
        if forced and len(selections[0]) < counts[0]:
            remaining = sorted(selections[0] - set(forced))
            selections[0] = set(forced) | set(
                rng.choice(remaining, len(selections[0]) - len(forced), replace=False)
            )
        offset = [0, 0]
        for j, (items, omits) in enumerate(runs):
            rec = {
                "positive": {},
                "negative": set(),
                "physical": set(),
                "done": set(),
                "occurrences": 0,
                "audit": 0,
                "self_positive": set(),
            }
            seen = set()

            for i, (c, status, g, sig, done) in enumerate(items, offset[0]):
                if i not in selections[0]:
                    continue
                rec["occurrences"] += 1
                if c in seen:
                    rec["physical"].add(c)
                seen.add(c)
                if g:
                    rec["positive"][c] = sig if sig is not None else c
                    rec["self_positive"].add(c)
                if status in (
                    "untriggered_rule",
                    "binding",
                    "guard",
                    "watermark",
                    "version",
                    "retired",
                    "hidden",
                ):
                    rec["negative"].add(c)
                if done:
                    rec["done"].add(c)
            for i, (c, g, sig) in enumerate(omits, offset[1]):
                if i in selections[1]:
                    rec["positive"][c] = sig if sig is not None else c
                    rec["audit"] += 1
            records[branch, j] = rec
            offset[0] += len(items)
            offset[1] += len(omits)
    return records


def contrasts(records):
    good = defaultdict(list)
    done = defaultdict(list)
    for key, r in records.items():
        for c in r["positive"]:
            good[c].append(key)
        for c in r["done"]:
            done[c].append(key)
    result = []
    for c in sorted(good.keys() & done.keys(), key=lambda x: (x.rule, x.refs)):
        for a in good[c]:
            for b in done[c]:
                # Positive request IDs are trajectory-local. Initial immutable owner IDs
                # can be compared across native forks of the same compiled program.
                if comparable(c, a, b):
                    result.append((a, b, c))
    return result


def inventory(root, prior, datasets=()):
    pair_counts = Counter()
    pure_effects = set()
    issued_computations = set()
    pure_issued = set()
    kinds = Counter()
    buckets = defaultdict(Counter)
    states = set()
    effects = set()
    named_effects = set()
    by_state = defaultdict(set)
    transition = Counter()
    paths = [
        path
        for dataset in (root, *datasets)
        for path in sorted((dataset / "buffer").glob("*.gz"))
    ]
    for path in paths:
        sh = load_shard(path)
        idx, b = sh["idx"], sh["branch"]
        folder = prior / "programs" / f"{idx:04d}"
        single = schema(json.loads((folder / "program.json").read_bytes()))
        stats = buckets[b]
        stats["episodes"] += 1
        live = {}
        dirty = {}
        former = {}
        has_lost = set()
        success = set()
        consumed = set()
        depth = {}
        published_run = {}
        seq = defaultdict(list)
        schedule = [s for s in sh["scheduler"] if not s[3]]
        for e, s, decoded in zip(
            sh["events"], schedule, decode(sh, single), strict=True
        ):
            frame = e["frame"]
            sid = (idx, frame["run"], e["semantic_state"], tuple(map(tuple, s[4])))
            states.add(sid)
            if b == 2:
                by_state["pure"].add(sid)
            stats["states"] += 1
            stats["direct_omissions"] += len(e["omitted"])
            stats["unknown_forks"] += int(not e["stable"])
            for rid, wm, d in s[4]:
                if rid in dirty:
                    transition[f"dirty_{int(dirty[rid])}_to_{int(d)}"] += 1
                dirty[rid] = d
            for q in frame["retired"]:
                live.pop((q["token"], q["op"]), None)
                transition["retirements"] += 1
            for q, row in frame["updates"]:
                key = (q["token"], q["op"])
                v = row["version"]
                if key in live and live[key] != v:
                    transition["owner_port_version_changed"] += 1
                if row["forwarded"]:
                    transition["forwarded_updates"] += 1
                live[key] = v
            items, omits = decoded
            stats["physical_repeats_in_page"] += len(items) - len(
                {row[0] for row in items}
            )
            stats["assisted_tokens_separate"] += len(e["assisted"])
            for (c, status, g, sig, done), res in zip(
                items, e["response"], strict=True
            ):
                issued_computations.add((sid, c))
                if b == 2:
                    pure_issued.add((sid, c))
                stats["tokens"] += 1
                stats[status] += 1
                stats["effective_ops"] += g
                if g:
                    success.add(res[0])
                    ancestors = {t for t, op, v in c.refs if t in success}
                    depth[res[0]] = 1 + max((depth[t] for t in ancestors), default=0)
                    published_run[res[0]] = frame["run"]
                    stats["chain_3_or_more_endpoint_tokens"] += int(depth[res[0]] >= 3)
                    stats["cross_run_positive_consumer_tokens"] += int(
                        any(published_run[t] < frame["run"] for t in ancestors)
                    )
                    if c in has_lost:
                        stats["exact_token_productive_again"] += 1
                        has_lost.discard(c)
                    for t, op, v in c.refs:
                        if t in success:
                            consumed.add((t, res[0]))
                label = (
                    f"gain_{g}"
                    if g
                    else ("witnessed_already_present" if done else status)
                )
                seq[c].append((frame["run"], label))
                if g:
                    former[c] = True
                if (
                    c in former
                    and not g
                    and status in ("untriggered_rule", "watermark")
                ):
                    has_lost.add(c)
                if done:
                    stats["witnessed_already_present"] += 1
                if g:
                    named_effects.add((sid, c))
                    if sig is not None:
                        effects.add((sid, sig))
                        if b == 2:
                            pure_effects.add((sid, sig))
            for c, g, sig in omits:
                named_effects.add((sid, c))
                if sig is not None:
                    effects.add((sid, sig))
                    if b == 2:
                        pure_effects.add((sid, sig))
        for history in seq.values():
            distinct = defaultdict(set)
            for r, label in history:
                distinct[label].add(r)
            for i, l in enumerate(sorted(distinct)):
                for m in sorted(distinct)[i + 1 :]:
                    if len(distinct[l] | distinct[m]) > 1:
                        kinds[l + " / " + m] += 1
                        pair_counts[l + " / " + m] += len(distinct[l]) * len(
                            distinct[m]
                        ) - len(distinct[l] & distinct[m])
        stats["direct_witnessed_parent_child_edges"] += len(consumed)
        stats["repair_events"] += len(sh["repair_events"])
        for k, v in zip(
            ("birth", "write", "union", "visibility"),
            sh["signed_external"],
            strict=True,
        ):
            stats[k] += v
    return {
        "distinct_issued_state_named": len(issued_computations),
        "distinct_pure_issued_state_named": len(pure_issued),
        "cross_run_state_pairs": pair_counts,
        "pure_state_effects_single_output_lower_bound": len(pure_effects),
        "branches": buckets,
        "transition": transition,
        "distinct_states": len(states),
        "distinct_pure_states": len(by_state["pure"]),
        "state_effects_single_output_lower_bound": len(effects),
        "state_effective_named_including_omissions": len(named_effects),
        "cross_run_contrast_classes": kinds,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("--also", type=Path, nargs="*", default=[])
    p.add_argument("--bank", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    result = inventory(a.root, a.bank or a.root / "dynamic", a.also)
    (a.output or a.root / "transition-inventory.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
