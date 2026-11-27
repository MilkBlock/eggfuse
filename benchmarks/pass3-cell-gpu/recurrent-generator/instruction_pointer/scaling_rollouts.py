"""Recover current KV views for signed positive Cells in full archived training-program rollouts."""

import gzip
import json
import pickle
from collections import defaultdict

import torch

from cell_kv_runtime import native
from continuous_trials import setup
from incremental_native import Ledger
from joint_cell_corpus import read_rows
from partner_index_worlds import args
from scaling_archive import directory, snapshot_key


class SignedReplay:
    def __init__(self, events):
        self.pages = defaultdict(list)
        self.by_uid = {}
        for e in events:
            self.pages[e["page"]].append(e)
            self.by_uid[e["uid"]] = e
        self.i = 0
        self.rows = []

    def prepare(self, w):
        pass

    def generate(self, w, s, rng, slots):
        events = self.pages[self.i]
        self.i += 1
        if any((e["run"], e["epoch"]) != (s["run"], s["epoch"]) for e in events):
            raise ValueError("wrong archived page")
        tokens = [(e["tid"], tuple(map(tuple, e["refs"]))) for e in events]
        positives = [
            t
            for e, t in zip(events, tokens, strict=True)
            if e["effective_ops"] > 0
            and e["status"] == "accepted"
            and t[0] < w.primitives
        ]
        if positives:
            self.rows.append((s, positives))
        return tokens


def collect(a):
    d = directory(a)
    src = a.out / "continuous-cell-stream"
    files = [
        *src.glob("fact-full-*.pkl.gz"),
        *(a.out / "joint-cell-pretraining").glob("live-fact-full-*.pkl.gz"),
    ]
    out = {}
    records = []
    _n, w, ref = setup(a, "fact")
    for path in sorted(files):
        meta = json.loads(path.with_suffix("").with_suffix(".json").read_text())
        draw = meta["seed"] if path.parent == src else meta["draw"]
        data = read_rows(path)
        events = data[0] if isinstance(data, tuple) else data
        replay = SignedReplay(events)
        trace = Ledger()
        r = native(
            a,
            w,
            policy=replay,
            seed=draw,
            slots=6,
            submit_pages=2,
            receipt_memory=True,
            rule_state=True,
            reference=ref,
            execution_trace=trace,
        )
        if (r["graph"], r["ops"], r["stats"]["paid"]) != (
            meta["graph"],
            meta["ops"],
            meta["stats"]["paid"],
        ):
            raise ValueError(("rollout mismatch", path))
        for uid, e in replay.by_uid.items():
            actual = trace.entries[uid]
            for k in (
                "run",
                "epoch",
                "wm",
                "dirty",
                "tid",
                "rid",
                "refs",
                "status",
                "effective_ops",
            ):
                if actual[k] != e[k]:
                    raise ValueError((path, uid, k))
        for s, ts in replay.rows:
            out.setdefault(snapshot_key(s), (s, set()))[1].update(ts)
        records.append(path.name)
    dest = d / "fact-rollouts.pkl.gz"
    with gzip.open(dest, "wb") as f:
        pickle.dump(list(out.values()), f, protocol=5)
    (d / "rollouts.json").write_text(
        json.dumps(
            {
                "files": records,
                "states": len(out),
                "targets": sum(len(v) for _, v in out.values()),
            }
        )
    )


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        collect(args())
