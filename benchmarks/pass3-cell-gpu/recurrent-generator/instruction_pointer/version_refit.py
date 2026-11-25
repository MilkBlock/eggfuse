"""Same-architecture mark calibration. Learn only from disjoint source programs.
The existing Flow, GNN, ownership policy, budgets and on-line installer are frozen.
"""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import torch

from boundary_inputs import BASE, native
from discrete_cells import Cell, Memory, from_q, load_enc
from discrete_study import load
from recursive_coverage import Target, snapshot
from recursive_train import binary, folder, read
from region_bake import linked
from region_owner import Ownership
from scaling_bake import save
from transaction_native import execute

WEIGHTS = Path("run-recall/discrete-computation-flow")


def memory(data, case, actor):
    d = folder(data, case)
    prog = read(d / "program.json")
    enc, scorer = load_enc(prog, actor)
    ct = native(binary(data), "receipt-contract", d / "program.json")
    return Memory(enc, ct, linked(prog, read(BASE / "menu.json")), scorer)


def train(data, actor, out):
    tick = perf_counter()
    marks, _ = load(SimpleNamespace(out=WEIGHTS))
    rng = np.random.default_rng(851)
    labels = []
    counts = {}
    with torch.no_grad():
        for case in ("sum", "dot"):
            d = folder(data, case)
            m = memory(data, case, actor)
            tape = read(d / "tape.json")["requests"]
            credit = dict(
                native(
                    binary(data),
                    "replay",
                    d / "program.json",
                    d / "tape.json",
                    "time",
                    "--ept-origins",
                )["ept"]["origins"]
            )
            by_id = {q["token"]: q for q in tape}
            seen = Counter()
            targets = defaultdict(list)
            # First three credited examples per rule in source order; include rare rules.
            for q in tape:
                r = q["rule"]
                if credit[q["token"]] > 0 and seen[r] < 3:
                    targets[q["run"]].append(from_q(q))
                    seen[r] += 1
            count = 0
            cert = read(BASE / "donors.json")[case]
            for verified in cert["passed"]:
                w = verified["witness"]
                q = by_id[w[0]]
                u = cert["proposed"][verified["index"]]
                if (
                    not all(verified["checks"].values())
                    or json.dumps(u) != json.dumps(m.menu.get(q["rule"]))
                    or sum(credit[k] for k in w) <= 0
                ):
                    continue
                targets[q["run"]].append(Cell(q["rule"], from_q(q).refs, True))
                count += 1
            with (d / "memory.jsonl").open() as stream:
                for line in stream:
                    f = json.loads(line)
                    m.update(f)
                    for cell in targets.pop(f["run"], []):
                        if (
                            marks.draw(m, rng, Counter(), target=cell, records=labels)
                            != cell
                        ):
                            raise ValueError("unreachable training target")
                    if not targets:
                        break
            counts[case] = dict(
                primitive=sum(seen.values()), higher=count, rules=len(seen)
            )
    torch.manual_seed(851)
    x = torch.stack([a for a, _, _ in labels])
    y = torch.tensor([b for _, b, _ in labels], dtype=torch.float)
    opt = torch.optim.AdamW(marks.parameters(), lr=0.0005)
    losses = []
    # Fixed optimizer budget. No held-run checkpoint selection.
    for _ in range(4):
        for idx in torch.randperm(len(x)).split(256):
            loss = torch.nn.functional.binary_cross_entropy_with_logits(
                marks.choice(x[idx]).flatten(), y[idx]
            )
            opt.zero_grad()
            loss.backward()
            opt.step()
        losses.append(loss.item())
    torch.save(marks.state_dict(), out / "marks.pt")
    save(
        out / "fit.json",
        dict(
            counts=counts,
            seed=851,
            branches=len(labels),
            last_batch_losses=losses,
            wall=perf_counter() - tick,
            sha256=hashlib.sha256((out / "marks.pt").read_bytes()).hexdigest(),
        ),
    )


def assess(data, actor, out):
    with TemporaryDirectory() as tmp:
        dest = Path(tmp)
        with (out / "frontier.jsonl").open("w") as log:
            for case in ("fact", "loopfact", "sum-divisors"):
                d = folder(data, case)
                path = dest / "gold.json"
                target = Target(
                    read(d / "program.json"),
                    snapshot(data, d, "reference", "-", None, path)[0],
                )
                initial = target.match(snapshot(data, d, "reference", "-", 0, path)[0])
                for pages in (4, 32):
                    for block, arms in enumerate(
                        [("frozen", "refit"), ("refit", "frozen")]
                    ):
                        for arm in arms:
                            tick = perf_counter()
                            m = memory(data, case, actor)
                            marks, nets = load(SimpleNamespace(out=WEIGHTS))
                            if arm == "refit":
                                marks.load_state_dict(
                                    torch.load(out / "marks.pt", weights_only=True)
                                )
                            pol = Ownership(m, marks, nets, "empty", 4, 536, pages)
                            setup = perf_counter() - tick
                            a = execute(
                                data, case, study=pol, series=str(dest), seconds=240
                            )
                            if a["termination"] != "schedule_end":
                                raise ValueError("rollout did not reach native end")
                            graph = read(dest / (case + "-stream-multi") / "state.json")
                            facts = sorted(target.match(graph) - initial)
                            res = {
                                k: a[k]
                                for k in (
                                    "paid",
                                    "signed_ops",
                                    "state_sha",
                                    "wall",
                                    "verdicts",
                                    "ept",
                                    "eps",
                                    "runtime_setup_seconds",
                                )
                            }
                            res.update(
                                case=case,
                                pages=pages,
                                block=block,
                                arm=arm,
                                setup=setup,
                                covered=len(facts),
                                reference=len(target.gold) - len(initial),
                                facts=facts,
                            )
                            log.write(json.dumps(res) + "\n")
                            log.flush()
                    print(case, pages, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["train", "eval"])
    for n in ("data", "actor", "out"):
        p.add_argument(n, type=Path)
    args = p.parse_args()
    torch.set_num_threads(1)
    (train if args.mode == "train" else assess)(args.data, args.actor, args.out)
