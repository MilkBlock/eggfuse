"""Input identities and normalized structural overlap; never supplies online features."""

import hashlib
from pathlib import Path

import torch

from latent_cell_flow import TRAIN
from recursive_train import binary, folder, read
from response_study import HELD, OPEN, arguments, memory
from scaling_bake import save


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


@torch.no_grad()
def manifest(a):
    files = {}
    train = set()
    cases = (
        *TRAIN,
        "fact",
        "loopfact",
        "sum-divisors",
        "grammar-benefit-left-17119",
        HELD,
        OPEN,
    )
    for name in cases:
        d = folder(a.data, name.removesuffix("-roll"))
        for p in ("program.json", "tape.json", "memory.jsonl"):
            files[name + "/" + p] = sha(d / p)
        fork = a.forks / (name + ".jsonl")
        if fork.is_file():
            files["fork/" + name] = sha(fork)
        if name in TRAIN:
            m = memory(a, d)
            train.update(m.enc.cat.int_bake.key(u) for u in m.menu.values())
    train.update(read(a.out / "composition/fit.json")["signatures"])
    d = folder(a.data, HELD)
    u = read(d / "layouts.json")[0]
    m = memory(a, d, u)
    new = m.enc.cat.int_bake.key(u)
    gnn = set(
        read(Path("run-recall/parameterized-deep-ripsat/catalog.json"))[
            "structural_keys"
        ]
    )
    extra = folder(a.data, OPEN)
    unit = read(extra / "layouts.json")[0]
    open_key = memory(a, extra, unit).enc.cat.int_bake.key(unit)
    assert not ((train | gnn) & {new, open_key})
    for file in (
        a.actor,
        binary(a.data),
        a.compiler,
        a.rollout / "sum-issued.json",
        a.rollout / "sum-native-memory.jsonl",
        Path("run-recall/structural-reach/prefix.pt"),
        Path("run-recall/parameterized-deep-ripsat/event-gnn.pt"),
        a.data / "recursive-agent/multi.pt",
        a.data / "structured-retrieval/field.pt",
    ):
        files[str(file)] = sha(file)
    weights = {str(f.relative_to(a.out)): sha(f) for f in a.out.glob("*/*.pt")}
    save(
        a.out / "inputs.json",
        dict(
            base="e89c929e",
            files=files,
            weights=weights,
            normalized_held_signature=new,
            normalized_open_signature=open_key,
            exposed_train_higher=sorted(train),
            archived_gnn_catalog=len(gnn),
            intersects_archived_gnn=False,
        ),
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    manifest(arguments())
