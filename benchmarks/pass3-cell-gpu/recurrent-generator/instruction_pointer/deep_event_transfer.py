"""Evaluate templates omitted by hash from the entire ten-thousand-template fit."""

import argparse
from pathlib import Path

import torch

from anchor_set_audit import load_actor
from alternate_proofs import digest
from deep_event_recognition import evaluate
from deep_ripsat import depth
from protocol_experiment import dump
from recursive_train import read
from ripsat_layout import signatures
from ripsat_policy import CellScorer, GraphBank
from ripsat_replay import unpack
from train_ripsat import layout_id


@torch.no_grad()
def check(root, weights, out):
    archive = root / "unified-consumers"
    replay = read(archive / "replay.json")
    assert digest(archive / "catalog.json") == replay["catalog"]
    original = unpack(read(archive / "catalog.json"))
    observed = {
        i for name in ("sum", "dot") for i in replay["cases"][name]["complete_layouts"]
    }
    layouts = sorted(
        (
            original[i]
            for i in observed
            if depth(original[i]) >= 3 and int(layout_id(original[i])[:8], 16) % 8 == 0
        ),
        key=layout_id,
    )
    assert set(layouts).isdisjoint(unpack(read(out / "catalog.json")["layouts"]))
    actor = load_actor(weights, True)
    donor = read(root / "sum/program.json")
    cat = actor.catalog_type(donor)
    checkpoint = torch.load(out / "event-gnn.pt", weights_only=True)
    net = CellScorer(actor.width).eval()
    net.load_state_dict(checkpoint["model"])
    bank = GraphBank(layouts, cat, actor.template_graph(cat))
    checkpoint["codes"] = bank.encode(net)
    held = out / "held"
    held.mkdir(exist_ok=True)
    dump(held / "catalog.json", dict(layouts=layouts, signatures=signatures(donor)))
    torch.save(checkpoint, held / "event-gnn.pt")
    dump(
        held / "result.json",
        dict(
            layouts=len(layouts),
            programs={
                n: evaluate(root, held, n, len(layouts))
                for n in ("fact", "loopfact", "sum-divisors")
            },
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("root", "weights", "out"):
        p.add_argument(key, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    check(a.root, a.weights, a.out)
