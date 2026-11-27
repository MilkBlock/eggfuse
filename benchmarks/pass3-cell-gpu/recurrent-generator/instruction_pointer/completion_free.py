"""Unprompted GPU sampling followed by blind native submission from the same prefix."""

import random
from collections import Counter
from time import perf_counter

import numpy as np
import torch

from completion_context import SIZES, VARIANTS, directory, frames, native, read, write
from coverage_eval import choices
from discrete_cells import from_q
from discrete_draft import Cell
from discovery_sampling import Domain
from discovery_score import packet
from discovery_states import cli

BUDGETS = (1, 4, 16, 64, 256)


@torch.no_grad()
def evaluate(a, n, v, i, p):
    d = directory(a, n, v, i, p)
    path = d / f"free-{a.seed}.json"
    if path.exists():
        return
    m = frames(a, d)
    pages = {
        arm: choices(a, m, arm, 64, a.seed)[2]
        for arm in ["initial", "A", "B", "C"] + (["small"] if n == 4 else [])
    }

    def publish(frame):
        for page in pages.values():
            page.publication(frame)

    m.on_page_publication = publish
    try:
        import json

        with (d / "frames.jsonl").open() as f:
            for line in f:
                frame = json.loads(line)
                m.update(frame)
                if frame["run"] == 2:
                    break
        domain = Domain(m)
        # Shared noise across neural arms. No reference information available to decoding.
        batches = {}
        for arm in ["factored", *pages]:
            seed = a.seed + 9967 * i + 593 * p + 17
            rng = np.random.default_rng(seed)
            rand = random.Random(seed)
            cells = []
            portions = []
            previous = 0
            elapsed = 0
            for b in BUDGETS:
                width = b - previous
                start = perf_counter()
                if arm == "factored":
                    cells.extend(domain.draw("factored", rand, width))
                else:
                    page = pages[arm]
                    page.cap = width
                    cells.extend(x.cell for x in page.sample(m, (), 1, rng, Counter()))
                elapsed += perf_counter() - start
                portions.append((b, len(cells), elapsed))
                previous = b
            batches[arm] = (cells, portions)
    finally:
        m.on_page_publication = None
        m.close_observer()

    prefix = read(d / "prefix.json")
    gold = {from_q(q) for q in read(d / "verified.json")["requests"] if q["run"] == 2}
    results = []
    tape = d / f"free-requests-{a.seed}.json"
    for arm, (cells, portions) in batches.items():
        write(
            tape,
            dict(
                prefix,
                requests=prefix["requests"]
                + [packet(c, 2, 100001 + j) for j, c in enumerate(cells)],
            ),
        )
        rep = native(a, d, "replay", tape, 2, "--ept-origins")
        gains = dict(rep["ept"]["origins"])
        for b, end, secs in portions:
            part = [Cell(c.rule, c.refs) for c in cells[:end]]
            positive = set(part) & gold
            ops = sum(gains.get(100001 + j, 0) for j in range(end))
            if ops != len(positive):
                raise ValueError(
                    f"Native replay and verified set disagree in {d}, {arm}: {ops}/{len(positive)}"
                )
            results.append(
                dict(
                    arm=arm,
                    size=n,
                    variant=v,
                    instance=i,
                    order=p,
                    seed=a.seed,
                    slots=b,
                    issued=end,
                    valid_draws=sum(c in gold for c in part),
                    distinct=ops,
                    gold=len(gold),
                    seconds=secs,
                    accepted_full=rep["counts"]["accepted"] - len(prefix["requests"]),
                    native_counts_full=rep["counts"],
                )
            )
    tape.unlink()
    write(path, results)


if __name__ == "__main__":
    p = cli()
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--sizes", type=int, nargs="+", default=SIZES)
    p.add_argument("--variants", nargs="+", default=VARIANTS)
    p.add_argument("--instances", type=int, nargs="+", default=[80, 81])
    a = p.parse_args()
    torch.set_num_threads(1)
    for n in a.sizes:
        for v in a.variants:
            for i in a.instances:
                for order in (0, 1):
                    evaluate(a, n, v, i, order)
        print(a.seed, n, flush=True)
