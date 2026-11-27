"""Fresh native validation programs, generated after the inherited trigger checkpoint."""

import hashlib
import pickle

import torch

from cell_kv_runtime import native
from foundation_world import dataset, world
from partner_index_worlds import args
from prefix_train import make
from scaling_archive import directory

PROGRAMS = (185510, 185511)


def prepare(a):
    d = directory(a)
    dest = d / "fresh-validation.pkl"
    if dest.exists():
        return
    actor = make(a, "rel").actor
    rows = {}
    for i in PROGRAMS:
        w = world(a, actor, i, True, "multi")
        targets = dataset(a, w, d / f"verified-{i}.pkl")
        replay = {
            s["run"]: s
            for s, _ in native(
                a, w, teacher="primitive", receipt_memory=True, rule_state=True
            )
        }
        verified = []
        for prior, tokens in targets:
            s = replay[prior["run"]]
            if any(prior[k] != s[k] for k in prior):
                raise ValueError(
                    "validation state differs from verified native target context"
                )
            verified.append((s, tokens))
        rows[i] = (
            hashlib.sha256((w.dir / "program.json").read_bytes()).hexdigest(),
            verified,
        )
    tmp = dest.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(rows))
    tmp.replace(dest)


if __name__ == "__main__":
    torch.set_num_threads(1)
    prepare(args())
