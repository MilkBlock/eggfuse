"""Frozen and independent native execution, replacing only typed address selection."""

import json
from collections import Counter
from functools import cache
from itertools import product
from pathlib import Path
from time import perf_counter

import numpy as np
import torch

from address_centroids import Centroids
from address_scores import init_w
from address_verdicts import Probes
from draft_dispatch import Dispatch
from draft_multitarget import snapshots
from metal_scaling import CASES, models
from parallel_budget import args
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from resident_page import Page
from response_study import memory
from transaction_native import execute


@cache
def code(width, arm):
    dense = arm.startswith("direct")
    flags = f"#define MARK_H {width}\n#define SET_PAGE 1\n"
    if arm == "semantic-mlp":
        flags += "#define SEMANTIC_ADDRESS 1\n"
    if dense:
        flags += "#define DENSE_ADDRESS 1\n"
    if arm in ("direct-mlp", "direct-old"):
        flags += "#define DENSE_MLP 1\n"
    if arm in ("tree-fit", "direct-mlp", "semantic-mlp"):
        flags += "#define REFIT_ADDRESS_TREE 1\n"
    return torch.mps.compile_shader(
        flags + Path(__file__).with_name("draft_page.metal").read_text()
    )


class AddressPage(Page):
    def publication(self, frame):
        previous = self.last_rules
        super().publication(frame)
        if hasattr(self, "centroids"):
            self.centroids.update(frame, previous != self.last_rules)

    def sample(self, m, source, steps, rng, stats):
        if source or steps != 1:
            raise ValueError("address-only trial requires an empty independent page")
        cap = self.cap
        buffers = self.scratch(cap)
        draft, vec, jobs, _generated, *_ = buffers
        draft.zero_()
        vec.zero_()
        jobs.zero_()
        ctl = self.integers([0, 0, 0, cap, 0, 0, 0, 0, cap] + [0] * 7)
        cfg = self.integers(
            [
                cap,
                self.slots,
                self.pcs,
                self.tables,
                self.tabrows.data.shape[1],
                self.ownerpc.data.shape[1],
                self.len_vocab,
                self.rows.get(m.last, 0),
                int(rng.integers(1, 2**31)),
                0,
                self.width,
                2 * cap,
            ]
        )
        self.apply_marks(cfg, ctl, self.upload(m.context()), buffers, cap)
        reply = torch.cat((ctl, draft.flatten())).cpu()
        self.count["boundary_readbacks"] += 1
        self.count["download_bytes"] += reply.numel() * 4
        stats["template_reads"] += int(reply[15])
        stats["template_scores"] += int(reply[14])
        stats["edit_forward_calls"] -= 1
        return self.unpack(reply, 1, cap, stats, 16)


def setup(a, m, arm, cap):
    marks, rates = models("1M")
    marks.load_state_dict(
        torch.load(a.previous / "s243/1M-n1000000/weights.pt", weights_only=True)[0]
    )
    old = torch.cat([p.flatten() for p in marks.choice.parameters()]).detach()
    if arm in ("direct-mlp", "tree-fit", "semantic-mlp"):
        marks.choice.load_state_dict(
            torch.load(a.out / (arm + ".pt"), weights_only=True)
        )
    page = AddressPage(m, marks, rates, Counter())
    page.lib = code(page.width, arm)
    page.cap = cap
    if arm in ("direct-fit", "direct-dot"):
        w = (
            torch.load(a.out / "direct-fit.pt", weights_only=True)
            if arm == "direct-fit"
            else init_w()
        )
        page.weights = torch.cat((page.weights, w.flatten().to("mps")))
    elif arm in ("direct-mlp", "tree-fit", "semantic-mlp"):
        page.weights = torch.cat((page.weights, old.to("mps")))
    if arm == "semantic-mlp":
        page.centroids = Centroids(page)
    marks.resident_page = page
    return marks, rates, page


@torch.no_grad()
def native(a):
    jobs = list(product(a.cases, a.arms))
    for b in range(a.blocks):
        for case, arm in jobs if b % 2 == 0 else reversed(jobs):
            dest = (
                a.out / f"native-address/{case}/{arm}-k{a.cap}-p{a.pages}-b{b}"
            ).resolve()
            dest.mkdir(parents=True, exist_ok=True)
            if (dest / "run.json").exists():
                continue
            d = folder(a.data, case)
            start = perf_counter()
            m = memory(a, d)
            marks, rates, page = setup(a, m, arm, a.cap)
            pol = Dispatch(
                m, marks, {"flow": rates}, "empty", 1, 536, a.pages, mode="page"
            )
            setup_time = perf_counter() - start
            x = execute(a.data, case, study=pol, series=str(dest), seconds=a.seconds)
            work = dest / (case + "-stream-multi")
            tmp = dest / "ref.json"
            target = Target(
                read(d / "program.json"),
                snapshot(a.data, d, "reference", "-", None, tmp)[0],
            )
            initial = target.match(snapshot(a.data, d, "reference", "-", 0, tmp)[0])
            wall = setup_time + x["wall"] + x["runtime_setup_seconds"]
            facts = sorted(target.match(read(work / "state.json")) - initial)
            x.update(
                case=case,
                method=arm,
                cap=a.cap,
                pages=a.pages,
                block=b,
                covered=len(facts),
                reference=len(target.gold) - len(initial),
                facts=facts,
                cold_wall=wall,
                cold_eps=x["signed_ops"] / wall,
                device=dict(page.count),
            )
            (dest / "run.json").write_text(json.dumps(x) + "\n")
            print(
                case,
                arm,
                b,
                x["termination"],
                len(facts),
                x["paid"],
                round(wall, 2),
                flush=True,
            )


@torch.no_grad()
def frozen(a):
    for case, arm in product(a.cases, a.arms):
        dest = a.out / f"sample-{case}-{arm}.json"
        if dest.exists() and (a.out / f"semantic-sample-{case}-{arm}.json").exists():
            continue

        def mem(a, d, arm=arm):
            m = memory(a, d)
            m.page = setup(a, m, arm, 256)[2]
            return m

        probe = Probes(a, case, arm)
        rows = []
        for m, r, g in snapshots(a, case, "teacher", mem):
            # Sequential packs give actual cumulative samples, including failed draws.
            seen = set()
            complete = 0
            stats = Counter()
            rng = np.random.default_rng(536 + r)
            start = perf_counter()
            for cap, n in ((4, 4), (12, 16), (48, 64), (192, 256)):
                m.page.cap = cap
                items = m.page.sample(m, (), 1, rng, stats)
                for v in items:
                    probe.add(r, v.cell, (n, v.cell.higher))
                seen.update(v.cell for v in items)
                complete += len(items)
                rows.append(
                    {
                        "case": case,
                        "run": r,
                        "arm": arm,
                        "n": n,
                        "known": len(g),
                        "hits": len(seen & g.keys()),
                        "complete": complete,
                        "repeat": complete - len(seen),
                        "pivots": stats["device_pivot_visits"],
                        "template_reads": stats["template_reads"],
                        "seconds": perf_counter() - start,
                    }
                )
        (a.out / f"semantic-sample-{case}-{arm}.json").write_text(
            json.dumps(probe.score()) + "\n"
        )
        dest.write_text(json.dumps(rows) + "\n")
        print(case, arm, sum(r["hits"] for r in rows if r["n"] == 256), flush=True)


if __name__ == "__main__":
    p = args()
    p.add_argument("mode", choices=["native", "frozen"])
    p.add_argument("--cases", nargs="+", default=CASES)
    p.add_argument(
        "--arms",
        nargs="+",
        default=["original", "tree-fit", "direct-fit", "direct-mlp"],
    )
    p.add_argument("--blocks", type=int, default=2)
    p.add_argument("--cap", type=int, default=4)
    p.add_argument("--pages", type=int, default=2)
    p.add_argument("--seconds", type=int, default=240)
    a = p.parse_args()
    torch.set_num_threads(1)
    (native if a.mode == "native" else frozen)(a)
