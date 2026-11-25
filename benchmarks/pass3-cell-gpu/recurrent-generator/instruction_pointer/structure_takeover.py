"""Realized disjoint teacher takeovers and optimistic marginal terminal visits."""

import argparse
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from entry_marginal import path_costs
from protocol_experiment import dump
from receipt_bake import save
from receipt_takeover import replay_many
from recursive_train import binary, folder, read
from structure_recipe import Evidence, link, native_unit, root_instances


def measure(data, store, case):
    d = folder(data, case)
    e = Evidence(data, case)
    menu = link(e.t.program, read(store / "structure-book.json"))
    options = []
    for root, refs, bodies in root_instances(e.t, read(store / "catalog.json")):
        for pid, plan in menu.get(root["rule"], ()):
            tokens = e.match(plan, root, refs, bodies)
            if len(tokens) == len(plan):
                options.append((pid, plan, tuple(tokens)))
    children = {tok for _, _, tokens in options for tok in tokens[1:]}
    costs = path_costs(data, d, children)

    def value(tokens):
        c = sum((costs[t] for t in tokens[1:]), Counter())
        return c["removed_terminal_visits"] + c["unary_event_skips"], sum(e.ops[t] for t in tokens[1:])

    options.sort(key=lambda opt: (*value(opt[2]), opt[2]), reverse=True)
    taken, packed = set(), []
    for pid, plan, tokens in options:
        if taken.isdisjoint(tokens):
            packed.append((pid, plan, tokens))
            taken.update(tokens)
    union_cost = sum(costs.values(), Counter())
    verified = None
    if packed:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "pack.json"
            save(path, [native_unit(plan, tokens, e.t) for _, plan, tokens in packed])
            verified = replay_many(
                d,
                binary(data),
                path,
                [(i, tokens) for i, (_, _, tokens) in enumerate(packed)],
                e.t.tape,
                read(d / "capture.json"),
            )
    used = {tok for _, _, ts in packed for tok in ts[1:]}
    billed = sum((costs[t] for t in used), Counter())
    dump(
        store / f"{case}-takeover.json",
        {
            "full_options": len(options),
            "optimistic_union": union_cost,
            "packed_roots": len(packed),
            "packed_suffixes": len(used),
            "packed_extra_ops": sum(e.ops[t] for t in used),
            "packed_marginal": billed,
            "packed_net_ccp_saving": billed["suppressed_b_proposals"] - len(used),
            "native": verified,
            "witnesses": [[pid, ts] for pid, _, ts in packed],
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    torch.set_num_threads(1)
    for case in a.cases:
        measure(a.data, a.store, case)
