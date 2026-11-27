"""Common random numbers and fixed-width neural waves on teacher and autonomous states."""

import json
import random
from collections import Counter
from pathlib import Path
from time import perf_counter
import numpy as np
import torch
from coverage_eval import choices
from discovery_score import packet
from discovery_sampling import Domain, seed_for
from discovery_states import cli, read, replay, save
from discrete_draft import Cell
from query_environment import conditioned
from recursive_train import folder


def recovery(a):
    for seed in (9633, 5003):
        dest = a.out / "weights" / str(seed)
        dest.mkdir(parents=True, exist_ok=True)
        load = lambda name: torch.load(
            a.donor / "weights" / str(seed) / (name + ".pt"), weights_only=True
        )
        initial, trained = load("initial"), load("dual-witness")
        for name, sd in [
            ("initial", initial),
            ("dual-witness", trained),
            (
                "conservative",
                {k: torch.lerp(v, trained[k], 1 / 16) for k, v in initial.items()},
            ),
        ]:
            torch.save(sd, dest / (name + ".pt"))


def historical_native_trial(arm, kind, budget):
    return arm in {
        "factored",
        "initial",
        "dual-witness",
        "conservative",
        "isolate-no-inactive",
    }


@torch.no_grad()
def frozen(
    a,
    case,
    source,
    *,
    fit_seed=9633,
    states=8,
    destination="paired",
    native_trial=historical_native_trial,
):
    base = a.archive / source / case
    dest = a.out / destination / source / case
    dest.mkdir(parents=True, exist_ok=True)
    m = conditioned(a, folder(a.data, case), base / "scheduler.jsonl")
    pages = {
        arm: choices(a, m, arm, 64, fit_seed)[2] for arm in a.arms if arm != "factored"
    }

    def publish(frame):
        for page in pages.values():
            page.publication(frame)

    m.on_page_publication = publish
    all_runs = sorted(s["run"] for s in read(base / "states.json"))
    selected = {
        all_runs[i]
        for i in np.linspace(
            0, len(all_runs) - 1, min(states, len(all_runs)), dtype=int
        )
    }
    contexts = (
        read(a.archive / "dirty" / case / "contexts.json")
        if source == "rollout"
        else {}
    )
    for line in (base / "frames.jsonl").open():
        frame = json.loads(line)
        r = frame["run"]
        if r > max(selected):
            break
        m.update(frame)
        path = dest / f"{r}.json"
        if r not in selected or path.exists():
            continue
        if contexts:
            last, event, state, ctx = contexts[str(r)]
            m.last = tuple(last) if last else None
            m.event, m.state = torch.tensor(event), torch.tensor(state)
            torch.testing.assert_close(m.context(), torch.tensor(ctx), rtol=0, atol=0)
        tape = read(base / str(r) / "oracle.json")
        prior = [q for q in tape["requests"] if q["run"] < r]
        next_id = max((q["token"] for q in prior), default=0) + 1
        probe = dest / "probe.json"
        save(probe, dict(tape, requests=prior))
        base_rep = replay(a, case, probe, r, "--ept-origins")
        gold = {q["token"] for q, g in read(base / str(r) / "gold.json") if g > 0}
        trials = []
        torch.mps.synchronize()
        for draw in (0, 1):
            arms = a.arms if (draw + r) % 2 else a.arms[::-1]
            for arm in arms:
                rng = np.random.default_rng(seed_for(r, draw))
                rand = random.Random(seed_for(r, draw))
                if arm == "factored":
                    domain = Domain(m)
                cells = []
                waves = []
                for _ in range(16):
                    start = perf_counter()
                    batch = (
                        [v.cell for v in pages[arm].sample(m, (), 1, rng, Counter())]
                        if arm != "factored"
                        else list(domain.draw("factored", rand, 64))
                    )
                    elapsed = perf_counter() - start
                    cells.extend(batch)
                    waves.append((len(cells), elapsed))
                trials.append((arm, draw, cells, waves))
        physical = {Cell(c.rule, c.refs) for _, _, cells, _ in trials for c in cells}
        names = {
            c: i
            for i, c in enumerate(sorted(physical, key=lambda c: (c.rule, c.refs)), 1)
        }
        save(probe, dict(tape, requests=[packet(c, r, i) for c, i in names.items()]))
        rr = replay(a, case, base / str(r) / "oracle.json", r, "--recall", probe)
        verdict = {
            i: (owner, why) for run, i, owner, why in rr["recall_verdicts"] if run == r
        }
        if rr["unused_recall"] or set(verdict) != set(names.values()):
            raise ValueError("incomplete offline audit")
        result = []
        cache = {}
        for arm, draw, cells, waves in trials:
            for kind, budget in [
                ("slots", 64),
                ("slots", 256),
                ("slots", 1024),
                ("complete", 4),
                ("complete", 16),
                ("complete", 64),
            ]:
                end = (
                    budget // 64
                    if kind == "slots"
                    else next(
                        (i for i, (n, t) in enumerate(waves, 1) if n >= budget),
                        len(waves),
                    )
                )
                count = waves[end - 1][0]
                part = cells[: min(count, budget) if kind == "complete" else count]
                hits = [
                    owner
                    for c in part
                    for owner, why in [verdict[names[Cell(c.rule, c.refs)]]]
                    if why == "match" and owner in gold
                ]
                row = dict(
                    arm=arm,
                    draw=draw,
                    kind=kind,
                    budget=budget,
                    slots=end * 64,
                    completed=count,
                    proposed=len(part),
                    hit=len(hits),
                    reference_owners=len(gold),
                    distinct=len(set(hits)),
                    seconds=sum(t for _, t in waves[:end]),
                    censored=kind == "complete" and count < budget,
                )
                if native_trial(arm, kind, budget):
                    key = tuple(names[Cell(c.rule, c.refs)] for c in part)
                    if key not in cache:
                        rows = [packet(c, r, next_id + i) for i, c in enumerate(part)]
                        save(probe, dict(tape, requests=prior + rows))
                        rep = (
                            replay(a, case, probe, r, "--ept-origins")
                            if rows
                            else base_rep
                        )
                        receipts = Counter(rep["counts"]["rejected"])
                        receipts.subtract(base_rep["counts"]["rejected"])
                        for k in ("accepted", "duplicates"):
                            receipts[k] = rep["counts"][k] - base_rep["counts"][k]
                        if (
                            sum(receipts.values()) != len(rows)
                            or min(receipts.values()) < 0
                        ):
                            raise ValueError("native receipt mismatch")
                        origins = dict(rep["ept"]["origins"])
                        outcomes = [origins.get(q["token"], 0) for q in rows]
                        cache[key] = dict(
                            native=dict(+receipts),
                            positive_requests=sum(g > 0 for g in outcomes),
                            ops=sum(outcomes),
                        )
                    row.update(cache[key])
                result.append(row)
        save(path, result)
    m.close_observer()


if __name__ == "__main__":
    p = cli()
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--donor", type=Path, required=True)
    p.add_argument(
        "--arms",
        nargs="+",
        default=[
            "initial",
            "dual-witness",
            "conservative",
            "factored",
            *[
                "isolate-" + s
                for s in (
                    "self",
                    "omission",
                    "inactive",
                    "binding",
                    "repeat",
                    "edit",
                    "no-inactive",
                )
            ],
        ],
    )
    a = p.parse_args()
    torch.set_num_threads(1)
    recovery(a)
    for case in a.cases:
        for source in ("teacher", "rollout"):
            frozen(a, case, source)
