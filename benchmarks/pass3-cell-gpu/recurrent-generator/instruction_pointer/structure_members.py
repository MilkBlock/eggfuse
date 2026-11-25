"""Offline sensitivity to opening interior members instead of only the last member."""

import argparse
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from entry_closure import named
from int_parameters import link_layouts
from protocol_experiment import dump
from recursive_train import read
from structure_recipe import Evidence, shape_of


def missing_obligation(e, q, pair, refs):
    """Nearest direct consumer of the accepted pair's actual returned ports."""
    t = e.t
    body = set(pair[0]) | set(pair[1])
    exposed = set(refs)
    inherited = set()
    for tok in body:
        record = t.q[tok]
        inherited.update(map(named, record["parents"]))
        for pc in t.rules.rules[record["rule"]]["outputs"]:
            op = int(pc)
            version = t.snap.version(tok, op, record["run"] + 1)
            if version is not None and version == t.snap.version(tok, op, q["run"]):
                exposed.add((tok, op, version))
    consumers = sorted(e.uses[q["token"]])
    if not consumers:
        return "no_recorded_consumer", set()
    nearest = consumers[0][0]
    costs = []
    third = set()
    for run, child in consumers:
        if run != nearest:
            break
        missing = set()
        for ref in map(named, t.q[child]["parents"]):
            tok, op, version = ref
            if tok == q["token"] and version == t.snap.version(tok, op, q["run"] + 1):
                continue
            if ref not in exposed:
                missing.add(ref)
        # Only count a captured input if its exact version was still readable
        # at entry. Later native use is already certified by the teacher.
        carried = {ref for ref in inherited if t.snap.version(*ref[:2], q["run"]) == ref[2]}
        costs.append((len(missing - carried), len(missing)))
        if len(missing) == 1 and not missing.intersection(carried):
            ref = next(iter(missing))
            if t.snap.version(*ref[:2], q["run"]) == ref[2]:
                third.add(ref)
    outside, missing = min(costs)
    if outside:
        return "outside_pair_and_matched_inputs", third
    if missing:
        return "could_read_still_visible_matched_input", third
    return "all_named_inputs_on_pair", third


def examine(data, store, case):
    e = Evidence(data, case)
    t = e.t
    owners = defaultdict(set)
    for _, layout in link_layouts(t.program, read(store / "catalog.json")):
        for body in t.occasions(layout):
            if len(body) > 1:
                for tok in body:
                    owners[tok].add(tuple(body))
    counts = Counter()
    wider = Counter()
    reasons = Counter()
    one_more = Counter()
    one_more_ops = set()
    extra = set()
    witness = None
    for q in t.tape:
        refs = tuple(map(named, q["parents"]))
        if len(refs) > 2:
            sources = {ref[0] for ref in refs}
            # Pair only bodies incident on this *recorded* proof, and require
            # all inputs to belong to the pair after both bodies have published.
            touching = {
                body for tok in sources for body in owners.get(tok, ()) if t.q[body[-1]]["run"] < q["run"]
            }
            for a, b in combinations(touching, 2):
                if not set(a).isdisjoint(b) or not sources <= set(a + b):
                    continue
                if not (sources.intersection(a) and sources.intersection(b)):
                    continue
                wider["wider_root_proofs"] += 1
                wider["root_effective_operations"] += e.ops[q["token"]]
                wider["largest_arity"] = max(wider["largest_arity"], len(refs))
                break
        if len(refs) != 2 or refs[0][0] == refs[1][0]:
            continue
        bodies = [[b for b in owners.get(ref[0], ()) if t.q[b[-1]]["run"] < q["run"]] for ref in refs]
        # Only recorded input incidences: this is an offline sensitivity study,
        # and never produces runtime lookup tables or evaluation-trained recipes.
        pairs = ((a, b) for a in bodies[0] for b in bodies[1] if set(a).isdisjoint(b))
        best = -1
        evidence = set()
        best_with_extra = None
        for pair in pairs:
            counts["body_pair_occurrences"] += 1
            reason, third = missing_obligation(e, q, pair, refs)
            evidence.add(reason)
            for ref in third:
                extended, ts = e.mine(q, refs, pair, extra_ref=ref)
                credit = sum(e.ops[tok] for tok in ts[1:])
                one_more_ops.update(ts[1:])
                candidate = credit, len(ts) - 1, shape_of(extended)
                if best_with_extra is None or candidate > best_with_extra:
                    best_with_extra = candidate
            plan, tokens = e.mine(q, refs, pair)
            score = sum(e.ops[tok] for tok in tokens[1:])
            best = max(best, score)
            extra.update(tokens[1:])
            if score and (witness is None or score > witness["extra_ops"]):
                witness = {
                    "boundary": pair,
                    "tokens": tokens,
                    "extra_ops": score,
                    "shape": shape_of(plan),
                    "rules": [r for r, _, _ in plan],
                    "stages": [s for _, s, _ in plan],
                }
        if best_with_extra is not None:
            credit, n, shape = best_with_extra
            one_more["roots_with_one_live_external_ref_at_entry"] += 1
            one_more["roots_with_witnessed_suffix"] += int(n > 0)
            one_more["roots_with_positive_suffix"] += int(credit > 0)
            one_more["roots_with_multiple_suffix_steps"] += int(n > 1)
            one_more["roots_with_fanout"] += int(shape == "fanout")
            one_more["gross_extra_ops"] += credit
        if best >= 0:
            label = next(
                key
                for key in (
                    "all_named_inputs_on_pair",
                    "could_read_still_visible_matched_input",
                    "outside_pair_and_matched_inputs",
                    "no_recorded_consumer",
                )
                if key in evidence
            )
            reasons[label] += 1
            counts["distinct_root_proofs"] += 1
            counts["positive_roots"] += int(best > 0)
            counts["best_gross_extra_ops"] += best
    counts["distinct_extra_ops"] = sum(e.ops[tok] for tok in extra)
    one_more["union_extra_ops"] = sum(e.ops[tok] for tok in one_more_ops)
    dump(
        store / f"{case}-member-oracle.json",
        {
            "counts": counts,
            "first_consumption": reasons,
            "explicit_third_operand": one_more,
            "higher_arity_root": wider,
            "witness": witness,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data", type=Path)
    parser.add_argument("store", type=Path)
    parser.add_argument("cases", nargs="+")
    args = parser.parse_args()
    for name in args.cases:
        examine(args.data, args.store, name)
