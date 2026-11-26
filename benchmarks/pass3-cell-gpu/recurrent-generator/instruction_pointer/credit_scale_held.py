"""Independent rollouts on the eight structure-disjoint relation DAGs."""

import hashlib
import json
import os
import random
import subprocess
import tempfile
from collections import Counter
from math import prod
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import torch

from ccp_v01 import Client, offline_repairs, read_repairs
from cell_transaction import memory_frame
from credit_scale_buffer import submit
from discovery_sampling import Domain
from discovery_states import cli, read
from query_environment import conditioned, setup
from recursive_coverage import Target


@torch.no_grad()
def trial(a, d, arm, seed, initial, gold):
    program = d / "program.json"
    start = perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp)
        obs = dest / "scheduler"
        m = conditioned(a, d, obs)
        assert not m.menu
        if arm != "factored":
            cfg = SimpleNamespace(**(vars(a) | {"out": a.out / "weights" / str(seed)}))
            page = setup(cfg, m, arm, 128)[2]
        repairs = []
        rng = np.random.default_rng(108 + seed)
        rand = random.Random(108 + seed)
        with subprocess.Popen(
            [a.runtime_binary, "online-ccp-v0.1", program, "-", "audit", "--ept"],
            stdin=-1,
            stdout=-1,
            env=dict(os.environ, EGGFUSE_QUERY_OBSERVER=str(obs)),
        ) as proc:
            txn = Client(proc, 512, hashlib.sha256(program.read_bytes()).hexdigest())
            try:
                while True:
                    h = json.loads(proc.stdout.readline())
                    if "role" in h:
                        break
                    rows, hs, ret, acc = memory_frame(proc.stdout, h)
                    desc, repair_ops = read_repairs(proc.stdout, h)
                    if len(desc):
                        repairs.append((desc, repair_ops))
                    if h.get("final_publication"):
                        continue
                    txn.run = h["run"]
                    txn.epoch = h["epoch"]
                    updates = []
                    k = 0
                    for t, o, tab, v, fw, end in rows.tolist():
                        updates.append(
                            [
                                {"token": t, "op": o},
                                {
                                    "table": tab,
                                    "version": v,
                                    "forwarded": bool(fw),
                                    "hashes": hs[k:end].tolist(),
                                },
                            ]
                        )
                        k = end
                    m.update(
                        {
                            "run": h["run"],
                            "epoch": h["epoch"],
                            "rules": h["rules"],
                            "accepted": acc.tolist(),
                            "retired": [{"token": t, "op": o} for t, o in ret.tolist()],
                            "updates": updates,
                        }
                    )
                    if arm == "factored":
                        dom = Domain(m)
                        goal = min(128, dom.size)
                        cells = list(dom.draw("factored", rand, goal))
                    else:
                        goal = min(
                            128,
                            sum(
                                prod(page.sizes[t] for t in m.roles[r])
                                for r, _ in m.ids
                            ),
                        )
                        cells = []
                        for i in range(8):
                            if len(cells) >= goal:
                                break
                            page.cap = max(16, goal - len(cells))
                            cells.extend(
                                v.cell for v in page.sample(m, (), 1, rng, Counter())
                            )
                        cells = cells[:goal]
                    submit(txn, cells, 128)
                    txn.seal()
                elapsed = perf_counter() - start
            finally:
                txn.close()
                m.close_observer()
                proc.stdin.close()
                if proc.poll() is None and "role" not in h:
                    proc.kill()
        tape = dest / "issued.json"
        tape.write_text(
            json.dumps(
                {
                    "schema": "cell-token-replay/v2",
                    "program_sha256": hashlib.sha256(program.read_bytes()).hexdigest(),
                    "repair_events": list(offline_repairs(repairs)),
                    "requests": list(txn.offline_tape(txn.run)),
                }
            )
        )
        audit = json.loads(
            subprocess.check_output(
                [
                    a.runtime_binary,
                    "replay",
                    program,
                    tape,
                    "audit",
                    "--export",
                    dest / "end",
                    "--ept",
                ]
            )
        )
        assert audit["state_sha"] == h["state_sha"]
        ops = sum(audit["ept"]["signed_external"]) + sum(
            audit["ept"]["signed_internal"]
        )
        facts = sorted(gold.match(read(dest / "end")) - initial)
        return {
            "case": d.name,
            "arm": arm,
            "seed": seed,
            "paid": txn.paid,
            "ops": ops,
            "covered": len(facts),
            "reference": len(gold.gold) - len(initial),
            "graph": h["state_sha"],
            "facts": facts,
            "seconds": elapsed,
            "EPT": ops / max(1, txn.paid),
            "EPS": ops / elapsed,
        }


def main(a):
    base = a.previous / "held"
    rows = []
    for item in read(base / "corpus.json"):
        d = base / "programs" / f"{item['id']:04d}"
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "ref"
            cmd = [a.runtime_binary, "reference", d / "program.json", "-", "audit"]
            subprocess.run(
                [*cmd, "--export", tmp], stdout=subprocess.DEVNULL, check=True
            )
            gold = Target(read(d / "program.json"), read(tmp))
            subprocess.run(
                [*cmd, "0", "--export", tmp], stdout=subprocess.DEVNULL, check=True
            )
            initial = gold.match(read(tmp))
        for seed in a.seeds:
            for arm in a.arms:
                rows.append(trial(a, d, arm, seed, initial, gold))
        print("held DAG", d.name, flush=True)
    with (a.out / "held-dags.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    p = cli()
    p.add_argument("--arms", nargs="+", required=True)
    p.add_argument("--seeds", nargs="+", type=int, default=[9633, 5003])
    torch.set_num_threads(1)
    main(p.parse_args())
