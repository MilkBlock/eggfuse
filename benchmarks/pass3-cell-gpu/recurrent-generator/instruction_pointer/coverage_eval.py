"""Equal complete-token budgets on archived states; oracle access is restricted to scoring."""

import csv
import json
import random
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from address_runtime import native
from coverage_fit import ARMS, BUDGETS, SEEDS
from discovery_native import configure
from discovery_sampling import Domain, seed_for
from discovery_score import packet, write_csv
from discovery_states import cli, read, replay, save
from discrete_draft import Cell
from query_environment import conditioned, online_memory, setup
from recursive_train import folder


def choices(a, m, arm, cap, seed):
    cfg = SimpleNamespace(**(vars(a) | {"out": a.out / "weights" / str(seed)}))
    return setup(cfg, m, arm, cap)


@torch.no_grad()
def frozen(a, case, source, arms=ARMS, draws=5):
    base = a.archive / source / case
    dest = a.out / "frozen" / source / case
    dest.mkdir(exist_ok=True, parents=True)
    m = conditioned(a, folder(a.data, case), base / "scheduler.jsonl")
    pages = {
        (seed, arm): choices(a, m, arm, 256, seed)[2]
        for seed in a.seeds
        for arm in arms
    }

    def update(frame):
        for page in pages.values():
            page.publication(frame)

    m.on_page_publication = update
    selected = {s["run"] for s in read(base / "states.json")}
    contexts = (
        read(a.archive / "dirty" / case / "contexts.json")
        if source == "rollout"
        else {}
    )
    result = []
    for line in (base / "frames.jsonl").open():
        frame = json.loads(line)
        r = frame["run"]
        if r > max(selected):
            break
        m.update(frame)
        if r not in selected:
            continue
        if source == "rollout":
            last, event, state, ctx = contexts[str(r)]
            m.last = tuple(last) if last else None
            m.event, m.state = torch.tensor(event), torch.tensor(state)
            torch.testing.assert_close(m.context(), torch.tensor(ctx), atol=0, rtol=0)
        checkpoint = dest / f"run-{r}.csv"
        if checkpoint.exists():
            with checkpoint.open() as stream:
                result.extend(csv.DictReader(stream))
            continue
        start = len(result)
        dom = Domain(m)
        goal = min(256, dom.size)
        batches = {}
        effort = {}
        for draw in range(draws):
            batches[0, "factored", draw] = list(
                dom.draw("factored", random.Random(seed_for(r, draw)), goal)
            )
            effort[0, "factored", draw] = goal
            for (seed, arm), page in pages.items():
                rng = np.random.default_rng(seed_for(r, draw))
                items = []
                attempts = 0
                while len(items) < goal and attempts < 262144:
                    page.cap = max(16, goal - len(items))
                    if attempts:
                        page.cap = min(
                            2048,
                            max(
                                page.cap,
                                round(
                                    (goal - len(items)) * attempts / max(len(items), 1)
                                ),
                            ),
                        )
                    # Bucket diagnostic batch sizes to bound allocated Metal scratch.
                    page.cap = min(
                        2048, 1 << (page.cap - 1).bit_length(), 262144 - attempts
                    )
                    if len(page.buffers) > 12:
                        page.buffers.clear()
                    items.extend(i.cell for i in page.sample(m, (), 1, rng, Counter()))
                    attempts += page.cap
                effort[seed, arm, draw] = attempts
                batches[seed, arm, draw] = items[:goal]
        physical = {Cell(c.rule, c.refs) for cells in batches.values() for c in cells}
        names = {
            c: i
            for i, c in enumerate(sorted(physical, key=lambda c: (c.rule, c.refs)), 1)
        }
        tape = read(base / str(r) / "oracle.json")
        probe = dest / "requests.json"
        save(probe, dict(tape, requests=[packet(c, r, i) for c, i in names.items()]))
        v = replay(a, case, base / str(r) / "oracle.json", r, "--recall", probe)
        verdict = {
            i: (owner, why) for rr, i, owner, why in v["recall_verdicts"] if r == rr
        }
        assert not v["unused_recall"] and len(names) == len(verdict)
        gold = {q["token"] for q, gain in read(base / str(r) / "gold.json") if gain > 0}
        for (seed, arm, draw), cells in batches.items():
            for b in BUDGETS:
                part = cells[:b]
                receipts = [verdict[names[Cell(c.rule, c.refs)]] for c in part]
                hits = [
                    owner for owner, why in receipts if why == "match" and owner in gold
                ]
                matched = min(
                    len(part),
                    *(len(other) for (_, _, d), other in batches.items() if d == draw),
                )
                matched_hits = {
                    owner
                    for owner, why in receipts[:matched]
                    if why == "match" and owner in gold
                }
                result.append(
                    {
                        "source": source,
                        "case": case,
                        "run": r,
                        "fit_seed": seed,
                        "arm": arm,
                        "draw_seed": draw,
                        "budget": b,
                        "goal": min(goal, b),
                        "issued": len(part),
                        "attempts_full": effort[seed, arm, draw],
                        "matched": matched,
                        "matched_productive": len(matched_hits),
                        "productive": len(set(hits)),
                        "hit_draws": len(hits),
                        "untriggered": sum(
                            why == "untriggered_rule" for _, why in receipts
                        ),
                        "issued575": sum(c.rule == 575 for c in part),
                        "binding575": sum(
                            c.rule == 575 and why == "binding"
                            for c, (_, why) in zip(part, receipts, strict=True)
                        ),
                        "distinct575": len(
                            {
                                owner
                                for c, (owner, why) in zip(part, receipts, strict=True)
                                if c.rule == 575 and why == "match" and owner in gold
                            }
                        ),
                        "physical_repeat": len(part) - len(set(part)),
                        "unknown": sum(why == "off_reference" for _, why in receipts),
                    }
                )
        temporary = checkpoint.with_suffix(".tmp")
        write_csv(temporary, result[start:])
        temporary.replace(checkpoint)
    m.close_observer()
    write_csv(dest / "curves.csv", result)
    print("scored", case, source, len(result), flush=True)


def independent(a, arms=ARMS):
    root = a.out
    for fit_seed in a.seeds:
        draw = {9633: 536, 5003: 1129, 1777: 3449}[fit_seed]
        sub = SimpleNamespace(
            **(
                vars(a)
                | {
                    "out": root / "native" / str(fit_seed) / str(draw),
                    "generation_seed": draw,
                    "cap": 16,
                    "pages": 2,
                    "seconds": 300,
                    "blocks": 2 if draw == 536 else 1,
                    "arms": ["factored", *arms],
                }
            )
        )

        def make(args, m, arm, cap, fit_seed=fit_seed):
            return configure(
                args,
                m,
                "factored" if arm == "factored" else "D",
                cap,
                neural_setup=lambda cfg, mem, unused, n: choices(
                    a, mem, arm, n, fit_seed
                ),
            )

        def mem(args, d, dest, arm):
            return online_memory(args, d, dest, "A" if arm == "factored" else "D")

        native(sub, make, mem)


if __name__ == "__main__":
    p = cli()
    p.add_argument("mode", choices=["frozen", "native"])
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    a = p.parse_args()
    torch.set_num_threads(1)
    if a.mode == "native":
        independent(a)
    else:
        for c in a.cases:
            for src in ("teacher", "rollout"):
                frozen(a, c, src)
    torch.mps.synchronize()
