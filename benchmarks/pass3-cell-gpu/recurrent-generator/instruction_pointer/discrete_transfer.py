"""Transfer a frozen primitive-only edit learner to a newly compiled six-step fork/join."""

import argparse
import hashlib
from pathlib import Path
from types import SimpleNamespace

import torch

from discrete_cells import setup
from discrete_rollout import run
from discrete_study import save
from latent_composition import fixture
from recursive_train import read


def evaluate(args):
    cohorts = {"mixed": args.out, "primitive": args.out / "primitive-fit"}
    digests = {
        k: {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.glob("*.pt")}
        for k, directory in cohorts.items()
    }
    if (
        any(len(hashes) != 4 for hashes in digests.values())
        or read(cohorts["primitive"] / "fit.json")["signatures"]
    ):
        raise ValueError("both frozen checkpoints and a primitive-only fit are required")
    case = "edit-held-forkjoin6"
    deps = [(-1,), (0,), (0, -1), (1, 2), (0, 2), (3, 4)]
    d, unit, cert = fixture(args.root, args.compiler, case, "forkjoin6", 227, "fresh", dependencies=deps)
    mem = setup(args.root, d, args.actor, unit)
    sig = mem.enc.cat.int_bake.key(unit)
    old = set(read(Path("run-recall/parameterized-deep-ripsat/catalog.json"))["structural_keys"])
    old.update(v["signature"] for v in read(args.out / "holdout.json")["cases"].values())
    old.update(read(args.out / "fit.json")["signatures"])
    if sig in old or not all(cert["checks"].values()):
        raise ValueError("invalid structural holdout")
    rows = {}
    for cohort, directory in cohorts.items():
        for block in range(2):
            for primitive_only in [False, True] if block == 0 else [True, False]:
                a = SimpleNamespace(
                    root=args.root,
                    out=directory,
                    actor=args.actor,
                    case=case,
                    arms=["empty:4"],
                    seed=536,
                    waves=2,
                    seconds=60,
                    block=block,
                    primitive_only=primitive_only,
                )
                run(a)
                name = f"{case}__empty4{'prim' if primitive_only else ''}_w2_b{block}"
                rows[f"{cohort}-{name}"] = read(directory / (name + ".json"))
    # Identical physical addresses, menu, execution and action cost; replace only the
    # Higher representation with the primitive root for each paired sampling seed.
    ablation = []
    for seed in range(12):
        for collapse in [False, True] if seed % 2 == 0 else [True, False]:
            a = SimpleNamespace(
                root=args.root,
                out=cohorts["primitive"],
                actor=args.actor,
                case=case,
                arms=["empty:4"],
                seed=1564 + seed,
                waves=2,
                seconds=60,
                block=100 + seed,
                root_code_only=collapse,
            )
            run(a)
            suffix = "rootonly" if collapse else ""
            r = read(a.out / f"{case}__empty4{suffix}_w2_b{a.block}.json")
            ablation.append(
                dict(
                    seed=a.seed,
                    root_only=collapse,
                    paid=r["paid"],
                    covered=r["covered"],
                    eps=r["cold_eps"],
                    ept=r["ept"],
                    terminal=r["state_sha"],
                    selected=r["work"].get("selected_high", 0),
                    bound=r["work"].get("instantiated", 0),
                    complete=r["work"].get("higher_completed", 0),
                )
            )
    save(
        args.out / "transfer.json",
        dict(
            signature=sig,
            weights=digests,
            donor_counts=read(cohorts["primitive"] / "fit.json"),
            certificate=cert,
            runs=rows,
            structure_ablation=ablation,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("root", "out", "actor", "compiler"):
        p.add_argument(name, type=Path)
    torch.set_num_threads(1)
    evaluate(p.parse_args())
