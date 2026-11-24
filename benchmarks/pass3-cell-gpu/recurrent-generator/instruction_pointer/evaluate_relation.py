"""Evaluate exact scores, capped retrieval and asymmetric angular LSH on common sealed events."""

import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import json
from pathlib import Path

import torch
from alternate_proofs import digest
from anchor_set import Domains
from anchor_set_audit import check
from composition_relation import Relation
from higher_cell import read
from history import History
from prefix_policy import Policy, generate
from relation_cases import episodes, request
from rule_read import load_actor


@lru_cache(None)
def planes(width):
    return torch.randn(
        width + 1, 5, generator=torch.Generator().manual_seed(971 + width)
    )


def retrieve(q, k):
    # Equalize key norms without changing q.k; probe the exact hash bucket
    # and its five one-bit neighbors, then rerank the returned entries.
    norm = k.square().sum(-1)
    ext = torch.cat((k, (norm.max() - norm).clamp_min(0).sqrt()[:, None]), -1)
    proj = planes(k.shape[1])
    powers = 2 ** torch.arange(5)
    codes = ((ext @ proj >= 0).long() * powers).sum(-1).tolist()
    buckets = defaultdict(list)
    for i, code in enumerate(codes):
        buckets[code].append(i)
    code = int((((q @ proj[:-1]) >= 0).long() * powers).sum())
    return [
        i for c in [code, *[code ^ (1 << bit) for bit in range(5)]] for i in buckets[c]
    ]


def top(scores, indices, k):
    ordered = sorted(indices, key=lambda i: -scores[i])
    if len(ordered) <= k:
        return set(ordered)
    cutoff = scores[ordered[k]]
    return {i for i in ordered[:k] if scores[i] > cutoff}


def prefix(folder, base, runs):
    actor = load_actor(base, True)
    cat = actor.catalog_type(read(folder / "program.json"))
    history = History(cat, 3434, cache_ports=True)
    nodes = actor.template_graph(cat)
    rows = []
    confidence = []
    with (folder / "memory.jsonl").open() as stream:
        for line in stream:
            frame = json.loads(line)
            snap = history.snapshot(frame, frame["run"] in runs)
            if snap is None:
                continue
            mem = actor.memory(cat, snap, nodes)
            dom = Domains(mem)
            index = {p.address: i for i, p in enumerate(mem.ports)}
            for rid, refs in generate(actor, cat, mem, Policy(32)):
                if not refs or len({a for a, _ in refs}) > 2:
                    continue
                js = [index[a] for a in refs]
                pivot = next(
                    i
                    for i, j in enumerate(js)
                    if not cat.seminaive[rid] or mem.ports[j].version >= snap.rules[rid]
                )
                order = cat.read_order(rid, pivot, "source")
                v = 0.0
                for depth, i in enumerate(order):
                    ids = torch.tensor([js[i]])
                    if depth:
                        previous = torch.tensor([[js[k] for k in order[:depth]]])
                        raw = (
                            actor.pair_scores(
                                cat, mem, rid, order[:depth], previous, i, ids
                            )
                            - actor.thresholds[2]
                        )
                    else:
                        raw = (
                            actor.root_scores(cat, mem, rid, i, ids, dom)
                            - actor.thresholds[1]
                        )
                    v += torch.nn.functional.logsigmoid(raw).item()
                confidence.append(v)
                parents = []
                for a, op in refs:
                    t = history.inverse[a]
                    parents.append(
                        dict(
                            address=dict(token=t, op=op),
                            version=history.visible[t, op]["version"],
                        )
                    )
                rows.append(
                    dict(token=len(rows) + 1, run=snap.run, rule=rid, parents=parents)
                )
    return rows, confidence


@torch.no_grad()
def evaluate(folder, base, train, binary):
    model = Relation().eval()
    model.load_state_dict(torch.load(train / "model.pt", weights_only=True))
    config = read(train / "train.json")
    seen = set(config["signatures"])
    known = set(config["producers"])

    def parents(sig):
        groups = {role[0]: (role[1], role[2]) for role in sig[1]}
        return tuple(sorted(groups.values()))

    observed = [json.loads(sig) for sig in seen]
    pairs = {parents(s) for s in observed}
    within = {(s[0], parents(s)) for s in observed}
    seen_rules = {s[0] for s in observed}

    def split(s):
        if json.dumps(s) in seen:
            return "seen"
        if any(r[2] not in known for r in s[1]):
            return "new_producer"
        if s[0] not in seen_rules:
            return "new_consumer"
        if parents(s) not in pairs:
            return "new_combination"
        if (s[0], parents(s)) not in within:
            return "new_pair_for_schema"
        return "new_mapping"

    state = Counter()
    panels = []
    packets = []
    rule_size = Counter()
    cached = {}

    def collect(run, rid, store, keys, truth, x, y, flip):
        if rule_size[run, rid] + len(keys) > 16384:
            state["budget_omitted_candidates"] += len(keys)
            state["canonical_at_rule_cap"] += sum(k in truth for k in keys)
            return
        state["canonical_scored"] += sum(k in truth for k in keys)
        rule_size[run, rid] += len(keys)
        if y:
            q = model.vectors(*x, int(flip))
            k = model.vectors(*y, 1 - int(flip))
            sc = (q @ k.T).flatten().tolist()
            subset = retrieve(q, k)
        else:
            sc = model.unary(model.encoder(x[0])).flatten().tolist()
            subset = [0]
        ids = list(range(len(keys)))
        exact = top(sc, ids, 8)
        approx = top(sc, subset, 8)
        state["exact_ranked"] += len(sc)
        state["lsh_reranked"] += len(subset)
        if y:
            state["binary_exact_top8"] += len(exact)
            state["binary_retrieved_exact_top8"] += len(exact & approx)
        strata = []
        for ks in keys:
            s = store.iface.key(rid, ks, store.types)
            if s not in cached:
                cached[s] = split(s)
            strata.append(cached[s])
        panels.append((len(packets), sc, exact, approx, strata, bool(y)))
        packets.extend(request(run, rid, ks, store) for ks in keys)

    runs, truth, stats = episodes(folder, 32, 72331, collect)
    tape = read(folder / "tape.json")
    verdicts = []
    for start in range(0, len(packets), 20000):
        chunk = packets[start : start + 20000]
        for i, r in enumerate(chunk):
            r["token"] = i + 1
        checked = check(folder, binary, tape, chunk)["recall_verdicts"]
        if any(
            run != p["run"] or token != p["token"]
            for (run, token, _, _), p in zip(checked, chunk, strict=True)
        ):
            raise ValueError("receiver returned proposals out of order")
        verdicts.extend(checked)
    eligible = {w: split(sig) for w, (sig, n) in truth.items() if n in (1, 2)}
    binary_hits = defaultdict(set)
    stratum_counts = defaultdict(Counter)
    arms = defaultdict(Counter)
    hits = defaultdict(set)
    all_hits = defaultdict(set)
    fire = defaultdict(Counter)
    selected = defaultdict(lambda: defaultdict(list))
    ranks = defaultdict(list)
    for start, score, exact, approx, strata, is_binary in panels:
        event = defaultdict(lambda: [False, False])
        event["all"]
        for i, z in enumerate(score):
            run, _, w, reason = verdicts[start + i]
            s = strata[i]
            for st in ("all", s):
                event[st][0] |= w is not None
                event[st][1] |= z >= 0
                if is_binary and w is not None:
                    ranks[st].append(sum(v >= z for v in score))
            for arm, keep in (
                ("full", True),
                ("k8", i in exact),
                ("lsh8", i in approx),
                ("exact_emit", z >= 0),
                ("k8_emit", z >= 0 and i in exact),
                ("lsh8_emit", z >= 0 and i in approx),
            ):
                if not keep:
                    continue
                if arm.endswith("_emit"):
                    selected[arm][run, packets[start + i]["rule"]].append((z, w))
                arms[arm]["paid"] += 1
                stratum_counts[arm, s]["paid"] += 1
                if w is not None:
                    stratum_counts[arm, s]["valid"] += 1
                    if w in eligible and truth[w][1] == 2:
                        binary_hits[arm].add(w)
                if w is None:
                    arms[arm][reason] += 1
                else:
                    arms[arm]["accepted"] += 1
                    all_hits[arm].add(w)
                    if w in eligible:
                        hits[arm].add(w)
        for st, (valid, proposed) in event.items():
            fire[st]["events"] += 1
            fire[st]["actual"] += valid
            fire[st]["fire"] += proposed
            fire[st]["tp"] += valid and proposed
    base_rows, confidence = prefix(folder, base, set(runs))
    baseline = defaultdict(list)
    for row, (_, _, w, _) in zip(
        base_rows,
        check(folder, binary, tape, base_rows)["recall_verdicts"],
        strict=True,
    ):
        baseline[row["run"], row["rule"]].append((confidence[row["token"] - 1], w))
    group = lambda ws: Counter(eligible[w] for w in ws if w in eligible)

    def compare(choices):
        matched = [set(), set()]
        paid = 0
        for k, ours in choices.items():
            old = baseline[k]
            budget = min(len(old), len(ours))
            if not budget:
                continue
            while budget:
                ix = top([z for z, w in ours], range(len(ours)), budget)
                iy = top([z for z, w in old], range(len(old)), budget)
                if len(ix) == len(iy):
                    break
                budget = min(len(ix), len(iy))
            if budget:
                paid += len(ix)
                matched[0].update(old[i][1] for i in iy)
                matched[1].update(ours[i][1] for i in ix)
        return dict(
            paid_per_arm=paid, prefix=group(matched[0]), relation=group(matched[1])
        )

    return dict(
        mode="native shadow",
        runs=runs,
        reference_runs=read(folder / "capture.json")["runs"],
        sample_teacher=sum(q["run"] in runs for q in tape["requests"]),
        prefix_weights=digest(base),
        weights=digest(train / "model.pt"),
        receiver=digest(binary),
        domains=stats,
        work=state,
        required=group(eligible),
        fire=fire,
        counts=arms,
        unique_all={arm: len(ids) for arm, ids in all_hits.items()},
        per_run_all=[
            [
                run,
                sum(q["run"] == run for q in tape["requests"]),
                sum(
                    q["run"] == run and q["token"] in all_hits["exact_emit"]
                    for q in tape["requests"]
                ),
            ]
            for run in runs
        ],
        precision_by_signature={k + "/" + s: v for (k, s), v in stratum_counts.items()},
        binary_required=group(w for w in eligible if truth[w][1] == 2),
        binary_hits={k: group(v) for k, v in binary_hits.items()},
        hits={k: group(v) for k, v in hits.items()},
        binary_rank={s: dict(Counter(rs)) for s, rs in ranks.items()},
        matched={arm: compare(choices) for arm, choices in selected.items()},
        per_run=[
            [
                run,
                sum(
                    q["token"] in eligible for q in tape["requests"] if q["run"] == run
                ),
                sum(
                    q["token"] in hits["exact_emit"]
                    for q in tape["requests"]
                    if q["run"] == run
                ),
            ]
            for run in runs
        ],
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("folder", "base", "train", "binary", "output"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    a.output.write_text(
        json.dumps(evaluate(a.folder, a.base, a.train, a.binary), indent=2) + "\n"
    )
