"""Compile held layout signatures after freezing all weights; verify named CCP lowering on both guard arms."""

import argparse
import hashlib
import json
from pathlib import Path

import torch

from discrete_cells import setup
from discrete_rollout import run
from discrete_study import save
from latent_composition import fixture

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "out", "actor", "compiler"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    checkpoints = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in a.out.glob("*.pt")}
    assert set(checkpoints) == {"editor.pt", "mask.pt", "flow.pt", "marks.pt"}
    training_signatures = set(json.loads((a.out / "fit.json").read_text())["signatures"])
    records = {}
    for shape, scene, value in [
        ("chain3", "fresh", 71),
        ("chain5", "fresh", 83),
        ("diamond", "fresh", 101),
        ("shared", "fresh", 97),
        ("chain3", "guard_true", 41),
        ("chain3", "guard_false", 42),
        ("chain3", "partial", 53),
        ("chain3", "duplicate", 53),
    ]:
        a.case = "edit-held-" + shape + "-" + scene
        d, u, cert = fixture(a.root, a.compiler, a.case, shape, value, scene)
        m = setup(a.root, d, a.actor, u)
        signature = m.enc.cat.int_bake.key(u)
        if signature in training_signatures:
            raise ValueError(f"held layout overlaps training: {a.case}")
        records[a.case] = dict(signature=signature, certificate=cert)
        for a.block in range(2):
            a.seed = 536
            a.waves = 2
            a.seconds = 60
            order = ["editor:1", "mask:4", "flow:4", "empty:4", "supervised-empty:1", "raw:1"]
            a.arms = order if a.block == 0 else order[::-1]
            run(a)
        save(a.out / "holdout.json", dict(frozen_sha=checkpoints, cases=records))
