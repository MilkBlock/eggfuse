"""Measure the effect of swapping two concrete i64 costs on trained layout codes."""
import argparse
from pathlib import Path

import torch

from anchor_set_audit import load_actor
from higher_cell import read
from protocol_experiment import dump
from ripsat_policy import CellScorer, GraphBank
from ripsat_replay import unpack

SWAP = {1: 10**16, 10**16: 1}


def substitute(x):
    if isinstance(x, list):
        return [substitute(v) for v in x]
    if not isinstance(x, dict):
        return x
    if "literal" in x and x["sort"]["name"] == "i64":
        return {**x, "literal": SWAP.get(x["literal"], x["literal"])}
    new = {k: substitute(v) for k,v in x.items()}
    if x.get("call", {}).get("table", "").startswith("RipenInput") and x.get("args"):
        new["args"][0] = x["args"][0]
    return new


@torch.no_grad()
def main(program, weights, old, new, out):
    donor = read(program)
    variant = dict(donor, recipe=substitute(donor["recipe"]),
                   merge_programs=substitute(donor["merge_programs"]))
    actor = load_actor(weights, True).eval()
    layouts = unpack(read(old / "catalog.json")["layouts"])
    if unpack(read(new / "catalog.json")["layouts"]) != layouts:
        raise ValueError("layout identity or order changed")
    results = {}
    for folder, parameterized in [(old, False), (new, True)]:
        net = CellScorer(actor.width).eval()
        net.load_state_dict(torch.load(folder / "event-gnn.pt", weights_only=True)["model"])
        codes = []
        for ir in [donor, variant]:
            cat = actor.catalog_type(ir, integer_parameters=parameterized)
            codes.append(GraphBank(layouts, cat, actor.template_graph(cat)).encode(net))
        diff = (codes[0] - codes[1]).abs().amax(1)
        results["parameterized" if parameterized else "legacy"] = dict(
            layouts=len(diff), changed=int(diff.count_nonzero()),
            above_1e_minus_6=int((diff > 1e-6).sum()), max_abs=float(diff.max()))
    dump(out, results)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("program","weights","legacy","parameterized","out"):
        p.add_argument(key, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    main(a.program, a.weights, a.legacy, a.parameterized, a.out)
