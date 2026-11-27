"""Export offline denominators and check normalized Higher structural holdouts."""

from collections import Counter

import torch

from cell_kv_runtime import logical_rows
from cell_kv_study import digest
from competition_corpus import KINDS, out, world
from competition_evaluate import zero_world
from completion_context import read
from partner_index_worlds import args
from selected_cell_study import model, store

if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    actor = model(a, 71, "direct", True).actor
    trained = set()
    for k in KINDS:
        for i in range(12):
            trained.update(digest(world(a, actor, k, i, True)))
    refs = []
    for k in (*KINDS, "zero1", "zero3"):
        for i in range(1 if k.startswith("zero") else 4):
            w = (
                zero_world(a, actor, int(k[-1]))
                if k.startswith("zero")
                else world(a, actor, k, i, False)
            )
            sigs = set(digest(w))
            if k != "single":
                assert not sigs & trained
            rows = logical_rows(read(w.dir / "reference.json"))
            refs.append(
                {
                    "kind": k,
                    "case": i,
                    "by_table": dict(Counter(t for t, v in rows)),
                    "trained_signature_overlap": len(sigs & trained),
                    "higher": len(sigs),
                }
            )
    store(out(a) / "reference-sets.json", refs)
