"""Matched frozen-state and CCP-native trials for parallel set pages."""

import json
from collections import Counter
from itertools import product
from time import perf_counter

import numpy as np
import torch

from draft_multitarget import snapshots
from metal_scaling import CASES, models
from parallel_budget import args
from parallel_fit import CAPS
from parallel_memory import make_memory
from parallel_page import JointPage, ParallelPolicy
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from transaction_native import execute


def load(a, arm):
    path = (
        a.previous / "s243/1M-n1000000/weights.pt"
        if arm == "independent"
        else a.out / (arm + ".pt")
    )
    pair = models("1M")
    for net, weights in zip(pair, torch.load(path, weights_only=True), strict=True):
        net.load_state_dict(weights)
        net.eval()
    return pair


def install(a, m, arm, cap):
    marks, rates = load(a, arm)
    page = JointPage(
        m, marks, rates, Counter(), ["independent", "editor", "flow"].index(arm), cap
    )
    marks.resident_page = page
    return marks, rates, page


def conditions(a):
    return [
        (arm, k, h)
        for arm, k, h in product(a.arms, a.caps, a.steps)
        if arm != "independent" or h == 1
    ]


@torch.no_grad()
def frozen(a):
    for case in a.cases:
        rows = []
        bins = Counter()
        pages = {}

        def setup(a, d, pages=pages):
            m = make_memory(a, d)
            for arm in a.arms:
                pages[arm] = install(a, m, arm, 4)[2]

            def publish(frame):
                for page in pages.values():
                    page.publication(frame)

            m.on_page_publication = publish
            return m

        for m, r, g in snapshots(a, case, "teacher", setup):
            b = min(3, (len(g).bit_length() - 1) // 2)
            if bins[b] >= a.per_bin:
                continue
            bins[b] += 1
            for arm, cap, steps in conditions(a):
                page = pages[arm]
                page.cap = cap
                page.history.zero_()
                rng = np.random.default_rng(43 + r)
                seen = set()
                hits = set()
                st = Counter()
                count = 0
                initial = page.count.copy()
                start = perf_counter()
                for w in range(1, a.pages + 1):
                    items = page.sample(m, (), steps, rng, st)
                    for i in items:
                        c = i.cell
                        count += 1
                        seen.add(c)
                        if c in g:
                            hits.add(c)
                    rows.append(
                        {
                            "case": case,
                            "run": r,
                            "arm": arm,
                            "slots": cap,
                            "steps": steps,
                            "page": w,
                            "known": len(g),
                            "hits": len(hits),
                            "ops": sum(g[c] for c in hits),
                            "issued_draft": count,
                            "unique": len(seen),
                            "time": perf_counter() - start,
                            "stats": dict(st),
                            "device": dict(page.count - initial),
                        }
                    )
        (a.out / f"frozen-{case}.json").write_text(json.dumps(rows) + "\n")
        print("frozen", case, bins, len(rows), flush=True)


@torch.no_grad()
def independent(a):
    jobs = list(product(a.cases, conditions(a)))
    for block in range(a.blocks):
        for case, (arm, cap, h) in jobs if block % 2 == 0 else reversed(jobs):
            dest = (
                a.out / f"native/{case}/{arm}-{cap}-{h}-p{a.pages}-b{block}"
            ).resolve()
            dest.mkdir(parents=True, exist_ok=True)
            output = dest / "run.json"
            if output.exists():
                continue
            d = folder(a.data, case)
            t = perf_counter()
            m = make_memory(a, d)
            marks, rates, page = install(a, m, arm, cap)
            pol = ParallelPolicy(
                m, marks, {"flow": rates}, "empty", h, 536, a.pages, mode="page"
            )
            if not a.pages:
                raise ValueError(
                    "use a positive evaluation page budget; empty pages are not fixed points"
                )
            setup = perf_counter() - t
            x = execute(a.data, case, study=pol, series=str(dest), seconds=a.seconds)
            work = dest / (case + "-stream-multi")
            tmp = dest / "reference.json"
            target = Target(
                read(d / "program.json"),
                snapshot(a.data, d, "reference", "-", None, tmp)[0],
            )
            init = target.match(snapshot(a.data, d, "reference", "-", 0, tmp)[0])
            covered = sorted(target.match(read(work / "state.json")) - init)
            wall = setup + x["wall"] + x["runtime_setup_seconds"]
            x.update(
                case=case,
                arm=arm,
                slots=cap,
                steps=h,
                pages=a.pages,
                block=block,
                facts=covered,
                reference=len(target.gold) - len(init),
                cold_wall=wall,
                cold_eps=x["signed_ops"] / wall,
                device_counts=dict(page.count),
                pending=sum(map(len, pol.delayed)),
            )
            x["direct_status"] = dict(Counter(str(v[4]) for v in pol.receipts))
            x["direct_kinds"] = dict(
                Counter(
                    "compute"
                    if v[3] in m.scalars
                    else "higher"
                    if v[5]
                    else "primitive"
                    for v in pol.receipts
                )
            )
            (dest / "receipts.json").write_text(json.dumps(pol.receipts) + "\n")
            output.write_text(json.dumps(x) + "\n")
            print(
                case,
                arm,
                cap,
                h,
                block,
                x["termination"],
                len(covered),
                x["paid"],
                x["signed_ops"],
                round(wall, 2),
                flush=True,
            )


if __name__ == "__main__":
    p = args()
    p.add_argument("mode", choices=["frozen", "native"])
    p.add_argument("--arms", nargs="+", default=["independent", "editor", "flow"])
    p.add_argument("--cases", nargs="+", default=CASES)
    p.add_argument("--caps", type=int, nargs="+", default=CAPS)
    p.add_argument("--steps", type=int, nargs="+", default=[1, 2, 4, 8])
    p.add_argument("--per-bin", type=int, default=1)
    p.add_argument("--pages", type=int, default=2)
    p.add_argument("--blocks", type=int, default=2)
    p.add_argument("--seconds", type=int, default=600)
    a = p.parse_args()
    torch.set_num_threads(1)
    (frozen if a.mode == "frozen" else independent)(a)
