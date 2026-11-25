"""Bind the actual initializer owner once. Read only compiled output PCs via CCP.
This witness-specific offline trial does not infer missing PCs or initial-fact owners.
"""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from boundary_inputs import CASE, binary, folder, read
from ccp_v01 import VALUE, Client, read_repairs
from cell_transaction import STATUS, memory_frame
from scaling_bake import save
from version_replay import PRIOR


def audit(data, out):
    d = folder(data, CASE)
    program = d / "program.json"
    compiled = read(program)["recipe"]["rules"][375]
    layouts = [r for r in read(PRIOR / "boundaries.json") if r["label"] == "after_init"]
    contract = json.loads(
        subprocess.check_output([binary(data), "receipt-contract", program])
    )
    exports = contract["rules"][375]["outputs"]
    cmd = [binary(data), "online-ccp-v0.1", program, "-", "time", "2"]
    results = []
    with subprocess.Popen(cmd, stdin=-1, stdout=-1) as proc:
        txn = Client(proc, 1024, hashlib.sha256(program.read_bytes()).hexdigest())
        try:
            for index in (1, 2, 3):
                f = json.loads(proc.stdout.readline())
                txn.run, txn.epoch = f["run"], f["epoch"]
                rows, *_ = memory_frame(proc.stdout, f)
                read_repairs(proc.stdout, f)
                if f["final_publication"]:
                    break
                if index == 1:
                    import numpy as np

                    ticket = txn.submit(
                        [[0, 0, 375, -1, 0]], np.empty((0, 4), dtype="int64")
                    )[0]
                    owner = int(ticket[0])
                    if ticket[1] != 0:
                        raise ValueError("initializer rejected")
                else:
                    live = {
                        (t, op): (table, v) for t, op, table, v, _, _ in rows.tolist()
                    }
                    rid = f["rules"][0][0]
                    for r in layouts:
                        ext = r["region"]["external"]
                        pcs = [pc for token, pc, v in ext if token == 1]
                        reads = []
                        for pc in pcs:
                            table, v = live[owner, pc]
                            if table != exports[str(pc)]["table"]:
                                raise ValueError(
                                    "Bake interface and publication differ"
                                )
                            reads.append([owner, pc, v, 0])
                        operations = [[2, 0, rid, -1, i + 1] for i in range(len(reads))]
                        reply = txn.collect(txn.enqueue(operations, reads, VALUE))
                        if set(reply.rows[:, 1].tolist()) != {STATUS.index("computed")}:
                            raise ValueError("declared projection failed")
                        wrong = [
                            [owner, pcs[0], live[owner, pcs[0]][1] + 1, 0],
                            [
                                owner,
                                len(compiled["effects"]) + 100,
                                live[owner, pcs[0]][1],
                                0,
                            ],
                        ]
                        invalid = txn.submit(operations[:2], wrong)
                        if [STATUS[int(n)] for n in invalid[:, 1]] != [
                            "version",
                            "unknown_output",
                        ]:
                            raise ValueError("projection failed open")
                        results.append(
                            dict(
                                root=r["root"],
                                slots=len(ext),
                                owners=len({t for t, pc, v in ext}),
                                addresses=len({(t, pc) for t, pc, v in ext}),
                                initializer_pcs=pcs,
                                other_refs=[p for p in ext if p[0] != 1],
                                confirmed_reads=len(reads),
                                publication_versions=dict(
                                    Counter(live[owner, pc][1] for pc in pcs)
                                ),
                                effects=dict(
                                    Counter(compiled["effects"][pc]["op"] for pc in pcs)
                                ),
                                paid_observations=len(reads) + 2,
                                invalid_status=invalid[:, 1].tolist(),
                            )
                        )
                txn.seal()
            end = json.loads(proc.stdout.readline())
            if end["committed_through_run"] != 2:
                raise ValueError("CCP projection did not seal")
        finally:
            proc.stdin.close()
            txn.close()
        if proc.wait():
            raise ValueError("CCP projection failed")
    save(out / "projection.json", results)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    audit(a.data, a.out)
