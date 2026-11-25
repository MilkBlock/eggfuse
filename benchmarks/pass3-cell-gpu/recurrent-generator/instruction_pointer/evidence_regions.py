"""Discover executable regions from the first publication of named evidence."""

import argparse
import heapq
import json
from bisect import bisect_left
from collections import Counter, defaultdict
from pathlib import Path

from entry_closure import named
from entry_marginal import path_costs
from evidence_witness import native_witness
from protocol_experiment import dump
from recursive_train import read
from structure_recipe import Evidence

OUTPUT, INPUT, PARTNER = -1, -2, -3
MAX_STEPS, HORIZON = 32, 32


def entry_events(e):
    seen = set()
    tabs = e.t.program["recipe"]["tables"]
    for line in (e.t.folder / "memory.jsonl").open():
        f = json.loads(line)
        run = f["run"]
        groups = defaultdict(dict)
        for a, row in f["updates"]:
            tok, pc = a["token"], a["op"]
            if tok not in seen:
                groups[tok][pc] = (tok, pc, row["version"])
        for tok, outputs in groups.items():
            seen.add(tok)
            if tok in e.t.q:
                source = ("rule", e.sigs[e.t.q[tok]["rule"]])
                inputs = tuple(map(named, e.t.q[tok]["parents"]))
            elif tok < 0 and tok % 2:
                pc = min(outputs)
                tab = e.initial_tables[tok, pc]
                source, inputs = ("initial", tabs[tab]["name"]), ()
            else:
                continue
            yield run, tok, source, outputs, inputs


def first_due(schedule, rule, ready):
    times = schedule[rule]
    i = bisect_left(times, ready)
    return times[i] if i < len(times) else None


def grow(e, entry, tok, known, direct, extra=None):
    lookup = dict(known)
    if extra:
        lookup[extra] = (PARTNER, 0)
    jobs = list(direct)
    heapq.heapify(jobs)
    visited = set()
    steps, commits = [], []
    while jobs and len(steps) < MAX_STEPS:
        run, t = heapq.heappop(jobs)
        if t in visited:
            continue
        visited.add(t)
        if run > entry + HORIZON:
            break
        q = e.t.q[t]
        args = tuple(map(named, q["parents"]))
        if not args or any(p not in lookup for p in args):
            continue
        wires = tuple(lookup[p] for p in args)
        # Every branch reads a published output or descends from one.
        if all(owner < 0 and owner != OUTPUT for owner, _ in wires):
            continue
        ready = max([entry, *(e.t.q[commits[i]]["run"] + 1 for i, _ in wires if i >= 0)])
        if first_due(e.t.schedule, q["rule"], ready) != run:
            continue
        owner = len(steps)
        steps.append((e.sigs[q["rule"]], wires))
        commits.append(t)
        for pc in e.t.rules.rules[q["rule"]]["outputs"]:
            pc = int(pc)
            version = e.t.snap.version(t, pc, run + 1)
            if version is not None:
                lookup[t, pc, version] = (owner, pc)
        for child in e.uses[t]:
            if child[0] > run:
                heapq.heappush(jobs, child)
    if extra:
        # One learned pointer instruction before search; its operands must be
        # available at publication. All subsequent occurrences reuse the binding.
        pivot = next(((s, w) for s, w in steps if (PARTNER, 0) in w), None)
        if pivot is None or pivot[1].count((PARTNER, 0)) != 1 or any(i >= 0 for i, _ in pivot[1]):
            return (), ()
        r = e.t.q[commits[steps.index(pivot)]]["rule"]
        if first_due(e.t.schedule, r, entry) != entry:
            return (), ()
    return tuple(steps), tuple(commits)


def build(data, store, case, compile_book=False):
    e = Evidence(data, case)
    e.initial_tables = {}
    for line in (e.t.folder / "memory.jsonl").open():
        for a, row in json.loads(line)["updates"]:
            if a["token"] < 0 and a["token"] % 2:
                e.initial_tables[a["token"], a["op"]] = row["table"]
    ranks, counts, hist = Counter(), Counter(), Counter()
    matches = []
    for run, tok, source, outputs, inputs in entry_events(e):
        counts["first_publications"] += 1
        known = {ref: (INPUT, j) for j, ref in enumerate(inputs) if e.t.snap.version(*ref[:2], run) == ref[2]}
        known.update({ref: (OUTPUT, pc) for pc, ref in outputs.items()})
        direct = [(r, t) for r, t in e.uses[tok] if run <= r <= run + HORIZON]
        partners = set()
        for r, t in direct:
            if r != run:
                continue
            refs = list(map(named, e.t.q[t]["parents"]))
            missing = [p for p in refs if p not in known]
            if len(missing) == 1 and e.t.snap.version(*missing[0][:2], run) == missing[0][2]:
                partners.add(missing[0])
        for partner in [None, *sorted(partners)]:
            plan, ts = grow(e, run, tok, known, direct, partner)
            if len(ts) < 2:
                continue
            k = 1 + int(partner is not None)
            ops = sum(e.ops[t] for t in ts)
            key = source, plan
            ranks[key] += ops / k
            roots = sum(all(i < 0 for i, _ in w) for _, w in plan)
            hist[k, ops] += 1
            matches.append((ops, k, roots, run, tok, ts, key))
    if compile_book:
        chosen = [key for key, _ in ranks.most_common(48) if ranks[key] > 0]
        dump(store / "evidence-book.json", {"training": case, "regions": chosen})
    convert = lambda p: (tuple(p[0]), tuple((r, tuple(map(tuple, w))) for r, w in p[1]))
    frozen = set(map(convert, read(store / "evidence-book.json")["regions"]))

    def census(options, measure_paths=False):
        covered, events = set(), set()
        ops = bindings = branches = stages = selected = 0
        best = Counter()
        evidence_counts = Counter()
        width = Counter()
        witness = None
        for event in sorted(options, key=lambda m: (-m[0] / m[1], -m[0], m[3:5], m[5])):
            n, k, b, run, tok, ts, _ = event
            if tok in events or not covered.isdisjoint(ts) or not n:
                continue
            if (
                measure_paths
                and witness is None
                and b >= 2
                and any(e.t.q[t]["run"] > e.t.q[ts[0]]["run"] for t in ts)
            ):
                witness = native_witness(e, data, event)
            selected += 1
            covered.update(ts)
            events.add(tok)
            ops += n
            bindings += k
            branches += max(0, b - 1)
            stages += sum(e.t.q[t]["run"] > run for t in ts)
            best[n / k] += 1
            evidence_counts[k] += 1
            width[b] += 1
        marginal = Counter()
        if measure_paths and covered:
            for cost in path_costs(data, e.t.folder, covered).values():
                marginal.update(cost)
        return {
            "native_witness": witness,
            "entry_binding_histogram": dict(evidence_counts),
            "direct_branch_histogram": dict(width),
            "teacher_fresh_path_costs": dict(marginal),
            "opportunities": len(options),
            "events": len({m[4] for m in options}),
            "selected": selected,
            "steps": len(covered),
            "effective_ops": ops,
            "independent_bindings": bindings,
            "extra_direct_branches": branches,
            "later_run_steps": stages,
            "EAR": ops / bindings if bindings else None,
            "packed_EAR_histogram": sorted(best.items()),
            "max_individual_EAR": max((m[0] / m[1] for m in options), default=0),
        }

    dump(
        store / f"{case}-evidence-audit.json",
        {
            "first_publications": counts["first_publications"],
            "reference_ops": sum(e.ops.values()),
            "bounded_local": census(matches),
            "exact_donor_shape": census([m for m in matches if m[-1] in frozen], True),
            "opportunity_histogram": [[k, n, c] for (k, n), c in sorted(hist.items())],
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    import torch

    torch.set_num_threads(1)
    for case in a.cases:
        build(a.data, a.store, case, case == "sum")
