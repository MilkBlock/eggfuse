"""Fingerprint the executable, training assets and evaluated interfaces."""

import argparse
from collections import Counter
from pathlib import Path
from generation_higher import BAKE, Layouts
from generation_frontier import CASES
from protocol_experiment import digest, dump
from recursive_train import binary, folder, read
from ripsat_layout import capture
from train_generation_targets import TRAIN


def manifest(root, out, donor_dir):
    artifacts = {
        "native": binary(root),
        "compose": root / "recursive-agent/multi.pt",
        "field": root / "structured-retrieval/field.pt",
        "route": root / "txn-study/model.pt",
        "chain_route": root / "txn-chain-study/model.pt",
        "typed": Path("run-recall/protocol-learning/model.pt"),
        "residual": Path("run-recall/computation-benefit/residual.pt"),
        "outcomes": out / "outcomes.pt",
        "higher": out / "higher.pt",
        "catalog": BAKE / "catalog.json",
        "codes": BAKE / "codes.pt",
    }
    cases = (*CASES, "grammar-17122", "grammar-36719037", *TRAIN)
    programs = {
        c: dict(
            program=digest(folder(root, c) / "program.json"),
            teacher=digest(folder(root, c) / "tape.json"),
        )
        for c in cases
    }
    seen = set()
    donor = read(donor_dir / "program.json")
    for dataset in (donor_dir, folder(root, "loopfact")):
        cat = Layouts(read(dataset / "program.json"))
        _, _, occs, _ = capture(dataset, donor, 10, grow_consumers=True)
        for choices in occs.values():
            for layout, rows in choices.items():
                if layout in cat.index and any(
                    ready and first for _, ready, first, _ in rows
                ):
                    seen.add(cat.original[cat.index[layout]])
    layouts = {}
    for c in ("fact", "sum-divisors"):
        cat = Layouts(read(folder(root, c) / "program.json"))
        counts = read(out / f"higher_{c}_mixed_0.json")["layouts"]["counts"]
        partitions = {}
        for key in ("issued_layouts", "completed_layouts"):
            by = Counter()
            for i, n in counts[key].items():
                by["seen" if cat.original[int(i)] in seen else "unseen"] += n
            partitions[key] = dict(by)
        layouts[c] = dict(
            eligible=len(cat.units),
            sizes=dict(Counter(map(len, cat.units))),
            positive_training_layouts=len(seen),
            **partitions,
        )
    dump(
        out / "manifest.json",
        dict(
            weights_and_build={k: digest(v) for k, v in artifacts.items()},
            programs=programs,
            layout_donor=digest(donor_dir / "program.json"),
            layout_recognition=layouts,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for arg in ("root", "out", "donor"):
        p.add_argument(arg, type=Path)
    a = p.parse_args()
    manifest(a.root, a.out, a.donor)
