"""Paired rule-56 interface diagnostic on actual CCP publications; no proof search."""

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from time import perf_counter

import numpy as np
import torch

from boundary_inputs import CASE, native
from ccp_v01 import VALUE, Client, read_repairs
from cell_transaction import STATUS, memory_frame
from discrete_cells import Marks, load_enc
from recursive_train import binary, folder, read
from scaling_bake import save
from version_replay import PRIOR


def bind(marks, context, members, vectors, rng, counts):
    lo, hi = 0, len(members)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        a, b = members[(lo + mid - 1) // 2], members[(mid + hi - 1) // 2]
        logit = marks.choice(marks.branch(context, vectors[a], vectors[b], 1))
        counts[0] += 1
        if rng.random() < logit.sigmoid().item():
            lo = mid
        else:
            hi = mid
    return members[lo]


@torch.no_grad()
def audit(data, actor, out):
    p = folder(data, CASE) / "program.json"
    enc, _ = load_enc(read(p), actor)
    marks = Marks().eval()
    marks.load_state_dict(
        torch.load("run-recall/discrete-computation-flow/marks.pt", weights_only=True)
    )
    ct = native(binary(data), "receipt-contract", p)["rules"][375]["outputs"]
    examples = [
        r for r in read(PRIOR / "boundaries.json") if r["label"] == "after_init"
    ]
    results = []
    version_checks = []
    with subprocess.Popen(
        [binary(data), "online-ccp-v0.1", p, "-", "time", "2"], stdin=-1, stdout=-1
    ) as proc:
        txn = Client(proc, 1024, hashlib.sha256(p.read_bytes()).hexdigest())
        live = {}
        try:
            for f in iter(lambda: json.loads(proc.stdout.readline()), None):
                if "role" in f:
                    break
                txn.run, txn.epoch = f["run"], f["epoch"]
                rows, hashes, retired, _ = memory_frame(proc.stdout, f)
                read_repairs(proc.stdout, f)
                for t, op in retired:
                    live.pop((int(t), int(op)), None)
                start = 0
                for t, op, tab, ver, fwd, end in rows.tolist():
                    live[t, op] = dict(
                        table=tab,
                        version=ver,
                        forwarded=bool(fwd),
                        hashes=hashes[start:end].tolist(),
                    )
                    start = end
                if f["final_publication"]:
                    continue
                if f["run"] == 1:
                    owner, status, *_ = txn.submit(
                        [[0, 0, 375, -1, 0]], np.empty((0, 4), np.int64)
                    )[0]
                    assert int(status) == 0
                    owner = int(owner)
                    txn.seal()
                    continue
                init = defaultdict(list)
                for (tid, op), r in live.items():
                    if tid < 0 and op == 0:
                        init[r["table"]].append(tid)
                owners = [tid for tids in init.values() for tid in tids] + [owner]
                vecs = dict(
                    zip(owners, enc.ports([live[t, 0] for t in owners]), strict=True)
                )
                for row in examples:
                    ext = row["region"]["external"]
                    # Offline specialization: introduce fresh symbolic group variables in first-use order.
                    names = {}
                    schema = []
                    for tid, op, v in ext:
                        slot = names.setdefault(tid, len(names))
                        tab = (
                            ct[str(op)]["table"] if tid == 1 else live[tid, op]["table"]
                        )
                        schema.append((slot, op, tab, tid == 1))
                    for block in range(4):
                        arms = (
                            ["port", "owner"] if block % 2 == 0 else ["owner", "port"]
                        )
                        pair = []
                        for mode in arms:
                            rng = np.random.default_rng(5321 + 997 * block)
                            begin = perf_counter()
                            memo = {}
                            calls = [0]
                            n = 0
                            refs = []
                            projection = 0.0
                            for slot, op, tab, generated in schema:
                                if mode == "port" or slot not in memo:
                                    domain = [owner] if generated else init[tab]
                                    # Couple random variates of repeated queries across the two arms.
                                    memo[slot] = bind(
                                        marks, enc.types[tab], domain, vecs, rng, calls
                                    )
                                    n += 1
                                tick = perf_counter()
                                t = memo[slot]
                                r = live[t, op]
                                if r["table"] != tab:
                                    raise ValueError("invalid compiled port role")
                                refs.append([t, op, r["version"], 0])
                                projection += perf_counter() - tick
                            bound = perf_counter()
                            ops = [
                                [2, 0, f["rules"][0][0], -1, i + 1]
                                for i in range(len(refs))
                            ]
                            rep = txn.collect(txn.enqueue(ops, refs, VALUE))
                            assert all(
                                STATUS[int(r[1])] == "computed" for r in rep.rows
                            )
                            pair.append(
                                (refs, rep.values.tobytes(), rep.value_ends.tobytes())
                            )
                            results.append(
                                dict(
                                    root=row["root"],
                                    block=block,
                                    mode=mode,
                                    slots=len(ext),
                                    bindings=n,
                                    forward=calls[0],
                                    paid=len(rep.rows),
                                    exact=sum(a[:3] == b for a, b in zip(refs, ext)),
                                    unique_roles=len(memo),
                                    bind_and_project=bound - begin,
                                    projection=projection,
                                    native_roundtrip=perf_counter() - bound,
                                    value_sha=hashlib.sha256(pair[-1][1]).hexdigest(),
                                )
                            )
                        assert pair[0] == pair[1]
                    invalid = [ref.copy() for ref in refs]
                    for ref in invalid:
                        ref[2] += 1
                    start = perf_counter()
                    rejected = txn.submit(ops, invalid)
                    elapsed = perf_counter() - start
                    assert all(STATUS[int(r[1])] == "version" for r in rejected)
                    version_checks.append(
                        {"root": row["root"], "checked": len(invalid), "wall": elapsed}
                    )
                txn.seal()
        finally:
            proc.stdin.close()
            txn.close()
        if proc.wait():
            raise RuntimeError("CCP exited with an error")
    save(out / "owner.json", results)
    save(
        out / "owner-native.json",
        {"native": f["txn_stats"], "wrong_version": version_checks},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("data", "actor", "out"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    audit(a.data, a.actor, a.out)
