"""Restore objective Response and rule state to older native counterfactual snapshots."""

import gzip
import pickle

import torch

from cell_kv_runtime import native
from partner_index_worlds import args
from prefix_train import make
from scaling_archive import directory
from state_transition_corpus import folder, world


class Replay:
    def __init__(self, path):
        self.path = iter(path)

    def prepare(self, w):
        pass

    def generate(self, w, s, rng, slots):
        return next(self.path, ())


def collect(a):
    actor = make(a, "rel").actor
    result = {}
    for i in range(12):
        w = world(a, actor, i, True)
        raw = pickle.loads((folder(a) / f"train-{i}.pkl").read_bytes())
        rows = []
        for path, record in raw["states"].items():
            labels = {
                t: l["gain"]
                for t, l in record["labels"].items()
                if l["positive"] and l["complete"] and not l["lost"]
            }
            if not labels:
                continue
            log = []
            native(
                a,
                w,
                policy=Replay(path),
                seed=2411 + i,
                slots=max([6, *map(len, path)]),
                rule_state=True,
                receipt_memory=True,
                receipt_log=log,
            )
            s = log[len(path)][0]
            if any(s[k] != v for k, v in record["state"].items()):
                raise ValueError("counterfactual snapshot mismatch")
            if tuple(tuple(x[1]) for x in log[: len(path)]) != path:
                raise ValueError("counterfactual prefix differs")
            rows.append((s, labels))
        result[i] = rows
    out = directory(a) / "transitions.pkl.gz"
    tmp = out.with_suffix(".tmp")
    with gzip.open(tmp, "wb") as f:
        pickle.dump(result, f, protocol=5)
    tmp.replace(out)


if __name__ == "__main__":
    torch.set_num_threads(1)
    collect(args())
