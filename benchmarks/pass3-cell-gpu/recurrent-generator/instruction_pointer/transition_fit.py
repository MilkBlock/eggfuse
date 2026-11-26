"""Fit one frozen architecture on quantity-matched native state distributions."""

import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
import torch
from torch.nn import functional as F

from address_scores import weight
from coverage_examples import pack
from coverage_onpolicy import coverage_gradient, freeze
from credit_scale_fit import load_shard
from discovery_states import cli
from query_environment import conditioned, setup
from query_fit import log_paths
from transition_credit import contrasts, reduce_data, schema


def load_program(root, i):
    return {
        b: load_shard(path)
        for b in (1, 2)
        for path in sorted((root / "buffer").glob(f"{i:04d}-{b}-*.gz"))
    }


def sample(seq, n, rng):
    seq = sorted(seq, key=lambda c: (c.rule, c.higher, c.refs))
    return (
        seq
        if len(seq) <= n
        else [seq[int(i)] for i in rng.choice(len(seq), n, replace=False)]
    )


@torch.no_grad()
def prepare(a, folder, shards, rec, keys, pairs, rng, gate, complete=False):
    needed = defaultdict(set)
    for x, y, c in pairs:
        needed[x].add(c)
        needed[y].add(c)
    for k in keys:
        needed[k]
    results = {}
    with tempfile.TemporaryDirectory() as td:
        for branch, sh in shards.items():
            observer = Path(td) / str(branch)
            observer.write_text(
                "".join(json.dumps(row) + "\n" for row in sh["scheduler"])
            )
            m = conditioned(a, folder, observer)
            if complete:
                cfg = SimpleNamespace(**(vars(a) | {"out": a.contract}))
                m.page = setup(cfg, m, "D", 256)[2]
            try:
                for j, e in enumerate(sh["events"]):
                    m.update(e["frame"])
                    k = branch, j
                    if k not in needed:
                        continue
                    torch.testing.assert_close(
                        m.context(), torch.tensor(e["context"]), atol=0, rtol=0
                    )
                    r = rec[k]
                    cells = (
                        set(sample(r["positive"], 48, rng))
                        | set(sample(r["negative"], 48, rng))
                        | set(sample(r["physical"], 32, rng))
                        | needed[k]
                    )
                    cells = sample(cells, len(cells), rng)
                    if not cells:
                        results[k] = None
                        continue
                    packet = pack(m, cells, gate, "offline", e["frame"]["run"])
                    results[k] = (
                        packet,
                        {c: i for i, c in enumerate(cells)},
                        r,
                        freeze(m) if complete and k in keys else None,
                    )
            finally:
                m.close_observer()
    return results


def probs(net, row):
    packet, index, _, _ = row
    return log_paths(net, packet, np.arange(len(index)), "mps").prod(-1)


def objective(net, row, budget, arm):
    if row is None:
        return next(net.parameters()).sum() * 0
    prob = probs(net, row)
    _, index, r, _ = row
    groups = defaultdict(list)
    for c, i in index.items():
        if c in r["positive"] and (arm != "no-omission" or c in r["self_positive"]):
            groups[r["positive"][c]].append(i)
    zero = prob.sum() * 0
    ids = [i for c, i in index.items() if c in r["negative"]]
    loss = prob[ids].sum() if ids else zero

    def discovery(mass):
        return -torch.expm1(budget * torch.log1p(-mass.clamp(max=1 - 1e-6)))

    if groups:
        probs_group = torch.stack([prob[ix].sum() for ix in groups.values()])
        loss = loss - discovery(probs_group).sum() / budget
    if arm == "flat":
        ids = [i for c, i in index.items() if c in r["physical"]]
        if ids:
            loss = loss + (prob[ids] - discovery(prob[ids]) / budget).sum()
    return loss


def complete_loss(net, row, budget, arm, gate, rng):
    if row is None:
        return next(net.parameters()).sum() * 0, 0, 0
    _, _, record, m = row
    credit = {
        c: s
        for c, s in record["positive"].items()
        if arm != "no-omission" or c in record["self_positive"]
    }

    def score(items):
        names = Counter(items)
        effects = Counter(credit[c] for c in items if c in credit)
        return [
            int(c in credit and effects[credit[c]] == 1)
            - int(c in record["negative"])
            - int(arm == "flat" and names[c] > 1)
            for c in items
        ]

    loss, _, slots, used = coverage_gradient(
        net, m, credit, gate, budget, rng, marginal=score
    )
    return loss, slots, used


def fit(a):
    large = a.size in ("large", "thin", "diverse")
    static = a.size == "static"
    complete = a.objective == "complete"
    tag = ("complete-" if complete else "") + a.size
    seeds = (9633, 5003)
    arms = (
        ["plain"]
        if static
        else ["plain", "flat", "paired", "no-omission"]
        if not large
        else ["plain", "paired"]
    )
    gate = weight(a).eval().to("mps")
    models = {}
    for seed in seeds:
        dest = a.out / "weights" / str(seed)
        dest.mkdir(exist_ok=True, parents=True)
        for arm in arms:
            net = weight(a).to("mps")
            net.load_state_dict(torch.load(a.initial, weights_only=True))
            models[seed, arm] = (net, torch.optim.AdamW(net.parameters(), lr=0.00015))
    samples = {k: np.random.default_rng(k[0] + 19) for k in models}
    stats = Counter()
    start = perf_counter()
    if a.programs > 256:
        raise ValueError("reserved evaluation graphs")
    order = np.random.default_rng(609).permutation(a.programs)
    for pos, i in enumerate(order):
        i = int(i)
        data = load_program(a.out, i)
        if a.size == "diverse":
            data[3] = load_program(a.out / "diverse", i)[2]
        if large:
            limits = {
                b: [
                    sum(len(e[f]) for e in sh["events"])
                    for f in ("generated", "omitted")
                ]
                for b, sh in data.items()
            }
        else:
            base = load_program(a.out / "static", i)
            limits = {
                b: [
                    min(
                        sum(len(e[f]) for e in sources[b]["events"])
                        for sources in (base, data)
                    )
                    for f in ("generated", "omitted")
                ]
                for b in (1, 2)
            }
            if static:
                data = base
        if a.size == "thin":
            limits = {
                b: [min(count, max(1, round(count * a.keep))) for count in counts]
                for b, counts in limits.items()
            }
        folder = (a.static_bank if static else a.previous) / "programs" / f"{i:04d}"
        rec = reduce_data(
            data, schema(json.loads((folder / "program.json").read_bytes())), limits, i
        )
        pairs = contrasts(rec)
        stats["signed_exposure"] += sum(v["occurrences"] for v in rec.values())
        stats["omission_exposure"] += sum(v["audit"] for v in rec.values())
        stats["decision_frames"] += len(rec)
        stats["semantic_contrast_pairs"] += len(pairs)
        for seed in seeds:
            rng = np.random.default_rng(seed + 131 * i)
            repeat = a.steps // a.programs + (pos < a.steps % a.programs)
            keys = sorted(rec)
            schedule = [keys[int(rng.integers(len(keys)))] for _ in range(repeat)]
            selected = (
                [pairs[int(rng.integers(len(pairs)))] for _ in schedule]
                if pairs
                else []
            )
            batch = prepare(
                a, folder, data, rec, schedule, selected, rng, gate, complete
            )
            budgets = (
                np.random.default_rng(seed + 773 * i).choice(
                    [4, 16, 64, 256], size=repeat
                )
                if large
                else None
            )
            for j, k in enumerate(schedule):
                budget = int(budgets[j] if large else rng.choice([4, 16, 64, 256]))
                for arm in arms:
                    net, opt = models[seed, arm]
                    opt.zero_grad()
                    if complete:
                        loss, slots, used = complete_loss(
                            net, batch[k], budget, arm, gate, samples[seed, arm]
                        )
                        stats["optimizer_slots"] += slots
                        stats["optimizer_complete_tokens"] += used
                    else:
                        loss = objective(net, batch[k], budget, arm)
                    if arm == "paired" and selected:
                        x, y, c = selected[j]
                        high = (
                            probs(net, batch[x])[batch[x][1][c]].clamp_min(1e-30).log()
                        )
                        low = (
                            probs(net, batch[y])[batch[y][1][c]].clamp_min(1e-30).log()
                        )
                        loss = loss + 0.05 * F.softplus(low - high)
                        stats["pair_updates"] += 1
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(
                        net.parameters(), 5, error_if_nonfinite=True
                    )
                    opt.step()
        if (pos + 1) % 16 == 0:
            print(tag, pos + 1, flush=True)
    torch.mps.synchronize()
    for (seed, arm), (net, _) in models.items():
        torch.save(
            net.cpu().state_dict(), a.out / "weights" / str(seed) / f"{tag}-{arm}.pt"
        )
    stats.update(
        {
            "programs": a.programs,
            "steps_per_fit": a.steps,
            "checkpoints": len(models),
            "seconds": perf_counter() - start,
        }
    )
    (a.out / f"fit-{tag}.json").write_text(json.dumps(stats, indent=2) + "\n")


if __name__ == "__main__":
    p = cli()
    p.add_argument("--initial", type=Path, required=True)
    p.add_argument("--static-bank", type=Path, required=True)
    p.add_argument(
        "--size",
        choices=["static", "dynamic", "thin", "large", "diverse"],
        required=True,
    )
    p.add_argument("--objective", choices=["slot", "complete"], default="complete")
    p.add_argument("--steps", type=int, default=384)
    p.add_argument("--keep", type=float, default=0.1)
    p.add_argument("--programs", type=int, default=32)
    torch.set_num_threads(1)
    fit(p.parse_args())
