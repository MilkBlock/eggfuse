"""Reconstruct the exact decision and retain only native origin-verified targets."""

import os
import pickle

import numpy as np
import torch

from binding_packets import public_view
from completion_context import native
from discrete_cells import from_q
from multirule_oracle import fork
from partner_index_worlds import args
from variable_binding_audit import run
from variable_completion import directory


def folder(a):
    d = directory(a).parent / "prefix-attention"
    d.mkdir(exist_ok=True)
    return d


def collect(a, case):
    d = folder(a)
    rows = []

    def visit(w, s, model, oldmem, case, rid, tape, prefix, archive):
        exact = native(
            a,
            a.data / case,
            "replay",
            archive / "accepted.json",
            s["run"] - 1,
            "--audit-next-proofs",
        )
        gold = [from_q(q) for q in exact if q["rule"] == rid]
        np.random.default_rng([113, s["run"], rid]).shuffle(gold)
        gold = gold[:32]
        gains, _ = fork(
            a, a.data / case, d / f"probe-{case}.json", tape, prefix, s["run"], gold
        )
        targets = [c.refs for c, g in zip(gold, gains, strict=True) if g > 0]
        z = public_view(oldmem, w.prog, key=(rid, False))
        assert all(
            set(refs) == {p[0] for p in s["ports"] if p[3] == table}
            for refs, table in zip(z["addrs"], w.roles[rid], strict=True)
        )
        rows.append((s, rid, targets, z))

    run(a, case, visit=visit)
    (d / f"{case}.pkl").write_bytes(pickle.dumps(rows, protocol=5))
    print(case, len(rows), sum(len(t) for _, _, t, _ in rows))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        collect(args(), os.environ["TR_CASE"])
