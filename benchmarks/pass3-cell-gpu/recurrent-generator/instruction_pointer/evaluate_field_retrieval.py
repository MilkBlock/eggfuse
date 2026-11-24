"""Frozen native shadow audit of block scoring, retrieval and matched complete-tuple ranking."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch

from alternate_proofs import digest
from anchor_set_audit import check
from composition_relation import Interfaces, Relation, Store
from evaluate_relation import prefix, retrieve
from field_retrieval import FieldEncoder, FieldIndex
from higher_cell import read
from relation_cases import request, select_runs
from retrieval_panels import (
    InterfaceRead,
    compose_scores,
    domain_size,
    panels,
    parents,
    retrieve_owners,
    topk,
)
from retrieval_prefix import PrefixRead
from rule_read import load_actor


def identities(config):
    seen = [json.loads(s) for s in config["signatures"]]

    def pair(sig):
        return tuple(sorted({r[0]: (r[1], r[2]) for r in sig[1]}.values()))

    pairs = {pair(sig) for sig in seen}
    consumers = {s[0] for s in seen}
    known = set(config["producers"])
    return lambda sig: (
        len(pair(sig)) == 2
        and pair(sig) not in pairs
        and sig[0] in consumers
        and all(r[2] in known for r in sig[1])
    )


@torch.no_grad()
def evaluate(root, case, out, initial=False):
    folder = root / case
    binary = root / "whole-fork-credit/receiver"
    base = root / "alternate-proofs/root-calibration/opaque-parent/calibrated/model.pt"
    frozen = root / "relation-experiment/train"
    model = Relation().eval()
    model.load_state_dict(torch.load(frozen / "model.pt", weights_only=True))
    torch.manual_seed(871)
    encoder = FieldEncoder().eval()
    if not initial:
        encoder.load_state_dict(torch.load(out / "field.pt", weights_only=True))
    index = FieldIndex(encoder)
    tape = read(folder / "tape.json")
    program = read(folder / "program.json")
    store = Store(Interfaces(program))
    actor = load_actor(base, True)
    old = PrefixRead(actor, actor.catalog_type(program))
    novel = identities(read(frozen / "train.json"))
    runs = set(select_runs(tape, read(folder / "capture.json")["runs"], 72331, 32))
    # Stratified workload-level quality diagnostic. Prepass uses only domain
    # cardinalities from the fixed snapshot sample, never teacher membership.
    remaining = 0
    count_store = Store(store.iface)
    for raw in map(json.loads, open(folder / "memory.jsonl")):
        count_store.advance(raw)
        if raw["run"] in runs:
            remaining += sum(
                domain_size(count_store, rid, wm) for rid, wm in raw["rules"]
            )
    old_report = (
        Path(__file__).parent / "run-recall" / "shared-composition" / (case + ".json")
    )
    quota = read(old_report)["work"]["exact_ranked"]
    budget_rng = np.random.default_rng(33615)
    targets = defaultdict(list)
    eligible = set()
    unseen = set()
    excluded = set()
    row_run = {}
    for p in tape["requests"]:
        if p["run"] not in runs:
            continue
        keys = tuple((a["address"]["token"], a["address"]["op"]) for a in p["parents"])
        t = p["token"]
        row_run[t] = p["run"]
        if 1 <= len({k[0] for k in keys}) <= 2:
            targets[p["run"], p["rule"]].append((t, keys))
            eligible.add(t)
    funnel = defaultdict(lambda: defaultdict(set))
    work = defaultdict(Counter)
    trace = defaultdict(dict)
    unique = {}
    packets = []
    rank = defaultdict(Counter)
    fair_rows = defaultdict(list)
    seq = np.random.default_rng(8849)
    for frame in map(json.loads, open(folder / "memory.jsonl")):
        run = frame["run"]
        store.advance(frame)
        index.advance(frame)
        old.advance(frame, run in runs)
        if run not in runs:
            continue
        for rid, wm in frame["rules"]:
            events, budget = panels(store, model, rid, wm)
            if not events:
                continue
            totals = sum(len(ix) for _, _, _, ix, _ in events)
            take = budget_rng.hypergeometric(quota, remaining - quota, totals)
            remaining -= totals
            quota -= take
            sample = np.sort(budget_rng.choice(totals, take, replace=False))
            offset = 0
            wanted = defaultdict(list)
            for t, ks in targets[run, rid]:
                if novel(store.iface.key(rid, ks, store.types)):
                    unseen.add(t)
                for owner in {k[0] for k in ks}:
                    roles = tuple(i for i, k in enumerate(ks) if k[0] == owner)
                    wanted[roles, tuple(ks[i] for i in roles)].append((t, ks))
            readers = {}
            for src, i, dst, ix, within_old in events:
                universe = np.arange(len(ix))
                z = compose_scores(src, i, dst, ix)
                where = {}
                for t, ks in wanted.get((src.roles, src.rows[i]), []):
                    j = dst.positions.get(tuple(ks[r] for r in dst.roles)) if dst else 0
                    if j is None:
                        continue
                    pos = np.searchsorted(ix, j)
                    if pos < len(ix) and ix[pos] == j:
                        where[pos] = t
                        if not within_old:
                            excluded.add(t)
                exact = topk(z, universe, 8)
                local = (
                    sample[
                        np.searchsorted(sample, offset) : np.searchsorted(
                            sample, offset + len(ix)
                        )
                    ]
                    - offset
                )
                offset += len(ix)
                candidates = {"dense": universe, "fixed": local}
                if dst:
                    mapkey = (src.roles, dst.roles)
                    if mapkey not in readers:
                        readers[mapkey] = InterfaceRead(index, store, rid, src, dst)
                    single, field, ann, ann_scores, eq = readers[mapkey].query(
                        store, src, i, ix
                    )
                    tie = seq.random(len(ix))
                    owners = dst.owners[ix]
                    candidates.update(
                        single=retrieve_owners(single, universe, owners, tie),
                        multi=retrieve_owners(field, universe, owners, tie),
                        multi_ann=retrieve_owners(ann_scores, ann, owners, tie),
                        hash_diagnostic=retrieve_owners(field[eq], eq, owners, tie),
                        hash_uncapped=eq,
                    )
                    field_order = np.lexsort((tie, -field))
                    ann_order = ann[np.lexsort((tie[ann], -ann_scores))]

                    def owner_top8(order):
                        _, first = np.unique(owners[order], return_index=True)
                        return owners[order[np.sort(first)[:8]]]

                    field_top8 = owner_top8(field_order)
                    ann_top8 = owner_top8(ann_order)
                    rank["multi_ann"]["field_exact_top8"] += len(field_top8)
                    rank["multi_ann"]["field_ann_hits"] += len(
                        np.intersect1d(field_top8, ann_top8)
                    )
                    work["multi_ann"]["retrieval_dot_candidates"] += len(ann)
                    work["multi"]["retrieval_dot_candidates"] += len(ix)
                    raw = np.array(
                        retrieve(src.vectors[i : i + 1], dst.vectors[ix]), dtype=int
                    )
                    candidates["legacy_ann"] = raw
                else:
                    for tag in (
                        "single",
                        "multi",
                        "multi_ann",
                        "hash_diagnostic",
                        "hash_uncapped",
                        "legacy_ann",
                    ):
                        candidates[tag] = universe

                def packet(j):
                    ks = parents(src, i, dst, ix[j])
                    key = run, rid, ks
                    if key not in unique:
                        idx = len(packets)
                        unique[key] = idx
                        packets.append(request(run, rid, ks, store))
                    return unique[key]

                def record(tag, ids, chosen, issued):
                    wk = work[tag]
                    wk["candidate_domain"] += len(ix)
                    wk["scored"] += len(ids)
                    wk["top8"] += len(chosen)
                    wk["issued"] += len(issued)
                    for stage, arr in [
                        ("domain", universe),
                        ("scored", ids),
                        ("top8", chosen),
                        ("issued", issued),
                    ]:
                        if where:
                            if stage == "domain":
                                funnel[tag][stage].update(where.values())
                            else:
                                funnel[tag][stage].update(
                                    where[int(j)] for j in arr if j in where
                                )
                    for j in issued:
                        pid = packet(j)
                        trace[tag][pid] = where.get(j)

                for tag, ids in candidates.items():
                    scores = (
                        z
                        if tag == "dense"
                        else compose_scores(src, i, dst, ix[ids])
                        if len(ids)
                        else np.empty(0)
                    )
                    local_top = topk(scores, np.arange(len(ids)), 8)
                    chosen = ids[local_top]
                    hot = local_top[scores[local_top] >= 0]
                    issued = ids[hot]
                    record(tag, ids, chosen, issued)
                    if dst:
                        rank[tag]["exact_top8"] += len(exact)
                        rank[tag]["retrieved"] += len(
                            np.intersect1d(exact, ids, assume_unique=True)
                        )
                        rank[tag]["after_rerank"] += len(
                            np.intersect1d(exact, chosen, assume_unique=True)
                        )
                    if tag in ("fixed", "multi_ann", "dense"):
                        for n in hot:
                            fair_rows[tag, run, rid].append(
                                (float(scores[n]), packet(ids[n]))
                            )
                # Vary the retrieval representation at identical shortlist, Compose and payment counts.
                n = min(len(candidates[k]) for k in ("single", "multi", "multi_ann"))
                for name in ("single", "multi", "multi_ann"):
                    ids = candidates[name][:n]
                    scores = compose_scores(src, i, dst, ix[ids]) if n else np.empty(0)
                    tie_values = tie[ids] if dst else np.zeros(n)
                    chosen = ids[np.lexsort((tie_values, -scores))[:8]]
                    record("matched_" + name, ids, chosen, chosen)
                if len(local):
                    ks = [parents(src, i, dst, ix[j]) for j in local]
                    pscore = old.scores(rid, int(src.first[i]), ks)
                    # Compare two ranking functions on exactly the same named tuples. Common paid cap,
                    # with deterministic, label-blind tie breaking and no score threshold for either.
                    m = min(8, len(local))
                    jitter = seq.random(len(local))
                    for tag, vals in [
                        ("paired_prefix", pscore),
                        ("paired_compose", z[local]),
                    ]:
                        chosen = local[np.lexsort((jitter, -vals))[:m]]
                        record(tag, local, chosen, chosen)
                else:
                    for tag in ("paired_prefix", "paired_compose"):
                        record(tag, local, local, local)
            assert offset == totals
    assert remaining == quota == 0
    # Independently compare actual generation paths at matched paid budget per rule and Run.
    base_rows, conf = prefix(folder, base, runs)
    baseline = defaultdict(list)
    for p, c in zip(base_rows, conf, strict=True):
        ks = tuple((a["address"]["token"], a["address"]["op"]) for a in p["parents"])
        k = p["run"], p["rule"], ks
        if k not in unique:
            unique[k] = len(packets)
            packets.append(p)
        baseline[k[:2]].append((c, unique[k]))
    for k, rows in fair_rows.items():
        kind, run, rid = k
        b = baseline[run, rid]
        limit = min(len(b), len(rows))
        for tag, items in [(kind + "_vs_prefix", b), (kind + "_vs_compose", rows)]:
            for z, pid in sorted(items, key=lambda x: -x[0])[:limit]:
                trace[tag][pid] = None
    verdict = []
    for start in range(0, len(packets), 16000):
        batch = packets[start : start + 16000]
        for i, p in enumerate(batch, 1):
            p["token"] = i
        rows = check(folder, binary, tape, batch)["recall_verdicts"]
        for (run, n, w, reason), p in zip(
            sorted(rows, key=lambda entry: entry[1]), batch, strict=True
        ):
            assert run == p["run"] and n == p["token"]
            verdict.append((w, reason))
    arms = {}
    for tag, items in trace.items():
        count = Counter()
        hits = set()
        for pid, canonical in items.items():
            w, reason = verdict[pid]
            if w is None:
                count["reject_" + reason] += 1
            else:
                hits.add(w)
                count["accepted"] += 1
                if canonical == w:
                    funnel[tag]["verified"].add(w)

        def summarize(group):
            return dict(
                targets=len(group),
                **{
                    s: len(funnel[tag][s] & group)
                    for s in ("domain", "scored", "top8", "issued", "verified")
                },
                any_proof=len(hits & group),
            )

        arms[tag] = dict(
            work=dict(work[tag]),
            paid=len(items),
            verdict=count,
            unique=len(hits),
            eligible=summarize(eligible),
            novel=summarize(unseen),
            layout_omitted=summarize(excluded),
            retrieval=rank[tag],
            per_run=[
                [
                    r,
                    sum(rr == r for rr in row_run.values()),
                    sum(row_run[t] == r for t in hits),
                ]
                for r in sorted(runs)
            ],
        )
    assert funnel["dense"]["domain"] == eligible
    return dict(
        mode="native shadow",
        reference_runs=read(folder / "capture.json")["runs"],
        runs=sorted(runs),
        teacher=len(row_run),
        receiver=digest(binary),
        compose=digest(frozen / "model.pt"),
        prefix=digest(base),
        fields="untrained-seed-871" if initial else digest(out / "field.pt"),
        field_writes=index.writes,
        field_removals=index.removes,
        arms=arms,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("root", "case", "out"):
        p.add_argument(name)
    p.add_argument("--initial", action="store_true")
    a = p.parse_args()
    out = Path(a.out)
    torch.set_num_threads(1)
    (out / (a.case + ("-initial.json" if a.initial else ".json"))).write_text(
        json.dumps(evaluate(Path(a.root), a.case, out, a.initial), indent=2) + "\n"
    )
