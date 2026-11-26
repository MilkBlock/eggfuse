"""Check complete device drafts against scalar execution, including local and stale references."""

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import torch

from discrete_cells import from_q
from discrete_draft import Cell, Item, Local, plan, valid
from metal_scaling import models
from page_reference import ScalarPage
from recursive_train import folder, read
from resident_page import Page
from response_study import memory


@torch.inference_mode()
def run(a):
    torch.set_num_threads(1)
    results = []
    for size in ["100K", "1M"]:
        for name in [
            "fact",
            "grammar-benefit-left-17119",
            "response-held-merge6",
            "sum-divisors",
        ]:
            d = folder(a.data, name)
            m = memory(a, d)
            net, rate = models(size)
            params = torch.load(
                a.out / "s243" / (size + "-n1000000") / "weights.pt", weights_only=True
            )
            net.load_state_dict(params[0])
            rate.load_state_dict(params[1])
            gm, gr = models(size)
            gm.load_state_dict(params[0])
            gr.load_state_dict(params[1])
            counts, stats = Counter(), Counter()
            page = Page(m, gm, gr, counts)
            scalar = ScalarPage(net, rate, Counter())
            tape = read(d / "tape.json")["requests"]
            byrun = {}
            for q in tape:
                byrun.setdefault(q["run"], []).append(from_q(q))
            earlier = {}
            tested = Counter()
            with (d / "memory.jsonl").open() as stream:
                for frame in map(json.loads, stream):
                    m.update(frame)
                    if not m.ids or frame["run"] not in byrun:
                        continue
                    things = byrun[frame["run"]]
                    earlier.update({q.rule: q for q in things})
                    srcs = [("empty", ()), ("bound", plan(things[:3]))]
                    cell = next((q for q in things if q.refs), None)
                    if cell:
                        ref = cell.refs[0]
                        srcs.append(
                            (
                                "stale",
                                plan(
                                    [
                                        Cell(
                                            cell.rule,
                                            ((*ref[:2], ref[2] - 1), *cell.refs[1:]),
                                        )
                                    ]
                                ),
                            )
                        )
                    # A local draft edge exercises stable IDs and protects dependent deletions.
                    for rid, h in m.ids:
                        match = next(
                            (
                                (rule, pc, i)
                                for rule, outs in enumerate(m.output_tables)
                                for pc, t in outs.items()
                                for i, tab in enumerate(m.roles[rid])
                                if rule in earlier
                                and t == tab
                                and any(q.rule == rid for q in things)
                            ),
                            None,
                        )
                        if match:
                            rule, pc, i = match
                            old = next(q for q in things if q.rule == rid)
                            srcs.append(
                                (
                                    "local",
                                    (
                                        Item(7, earlier[rule]),
                                        Item(
                                            9,
                                            Cell(
                                                old.rule,
                                                tuple(
                                                    Local(7, pc) if j == i else ref
                                                    for j, ref in enumerate(old.refs)
                                                ),
                                            ),
                                        ),
                                    ),
                                )
                            )
                            break
                    for kind, src in srcs:
                        for seed in range(8):
                            rng = np.random.default_rng(seed + 14519)
                            aa = scalar.sample(m, src, 4, rng, Counter())
                            bb = page.sample(
                                m, src, 4, np.random.default_rng(seed + 14519), stats
                            )
                            tested[kind] += 1
                            if not valid(bb, m.compatible) or aa != bb:
                                raise AssertionError(
                                    (name, size, frame["run"], kind, seed, aa, bb)
                                )
                    if tested["empty"] >= 32:
                        break
            results.append(
                {
                    "case": name,
                    "size": size,
                    "tests": dict(tested),
                    "metrics": dict(counts),
                }
            )
    (a.out / "page-parity.json").write_text(json.dumps(results) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--data", type=Path, default=Path("/tmp/dfm-local/data"))
    p.add_argument(
        "--actor", type=Path, default=Path("run-recall/higher-scaling/weights/actor.pt")
    )
    run(p.parse_args())
