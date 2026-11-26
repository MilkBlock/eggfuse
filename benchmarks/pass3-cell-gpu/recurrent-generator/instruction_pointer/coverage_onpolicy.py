"""Paired on-policy score gradient of budgeted distinct discovery with rejection sampling."""

import copy
import json
import random
import shutil
from collections import Counter
from types import SimpleNamespace

import numpy as np
import torch

from address_scores import weight
from coverage_examples import pack
from coverage_fit import BUDGETS, SEEDS, reject_loss
from discovery_sampling import Domain, seed_for
from discovery_score import write_csv
from discovery_states import cli
from discrete_draft import Cell
from draft_multitarget import snapshots
from parallel_fit import TRAIN
from query_environment import conditioned, setup
from query_fit import log_paths, read
from query_witnesses import groups


def freeze(m):
    # Only tensors/maps mutated by subsequent publications need private storage.
    frozen = copy.copy(m)
    frozen.pub = copy.copy(m.pub)
    frozen.pub.live = m.pub.live.copy()
    frozen.rows = copy.deepcopy(m.rows)
    frozen.index = m.index.copy()
    frozen.owner_rule = m.owner_rule.copy()
    page = copy.copy(m.page)
    page.m = frozen
    page.rows = m.page.rows.copy()
    page.addresses = m.page.addresses.copy()
    page.graphs = m.page.graphs.clone()
    page.sizes_gpu = m.page.sizes_gpu.clone()
    for name in ("tabrows", "ownerpc", "meta", "key", "member", "idvec"):
        slab = copy.copy(getattr(m.page, name))
        slab.data = slab.data.clone()
        setattr(page, name, slab)
    frozen.page = page
    return frozen


@torch.no_grad()
def collect(a):
    cfg = SimpleNamespace(**(vars(a) | {"out": a.contract}))
    result = {}
    for case, src in TRAIN:
        verified = groups(cfg, case, src, False)

        def build(args, d, case=case, src=src):
            m = conditioned(a, d, a.contract / f"state-{case}-{src}.jsonl")
            m.page = setup(cfg, m, "D", 256)[2]
            return m

        for m, r, g in snapshots(a, case, src, build):
            credit = {}
            for c, gain in g.items():
                if gain <= 0:
                    continue
                for alt in [c, *verified.get((r, c), ())]:
                    if alt in credit and credit[alt] != c:
                        raise ValueError("overlapping signatures")
                    credit[alt] = c
                    if (c.rule, True) in m.ids_index:
                        credit[Cell(c.rule, alt.refs, True)] = c
            result[f"{case}-{src}-{r:04}"] = (freeze(m), credit)
    if len(result) != 108:
        raise ValueError("incomplete training states")
    return [result[k] for k in sorted(result)]


def coefficients(first, second, credit):
    # Each held-out companion score has the same law as a completed draw,
    # independent of the leave-one-out contribution of the paired item.
    def singleton(items):
        sigs = [credit.get(c) for c in items]
        counts = Counter(sigs)
        return [int(g is not None and counts[g] == 1) for g in sigs]

    x, y = singleton(first), singleton(second)
    coeff = Counter()
    for c, d, h, k in zip(first, second, x, y, strict=True):
        coeff[c] += h - k
        coeff[d] += k - h
    return coeff


def coverage_gradient(net, m, credit, gate, budget, rng):
    if not credit:
        return next(net.parameters()).sum() * 0, 0, 0, 0
    with torch.no_grad():
        page = m.page
        params = torch.cat([p.ravel() for p in net.parameters()])
        page.weights[: len(params)].copy_(params)
        groups = max(1, 32 // budget)
        goal = 2 * budget * groups
        draws = []
        slots = 0
        # Rejection sampling of complete tokens. A numerical safety stop fails the
        # experiment explicitly rather than silently substituting shorter pages.
        while len(draws) < goal:
            if slots >= 2**21:
                raise RuntimeError("could not fill training budget")
            page.cap = 256
            draws.extend(i.cell for i in page.sample(m, (), 1, rng, Counter()))
            slots += 256
        coeff = Counter()
        discovery = 0
        for start in range(0, goal, 2 * budget):
            x = draws[start : start + budget]
            y = draws[start + budget : start + 2 * budget]
            coeff.update(coefficients(x, y, credit))
            discovery += sum(
                len({credit[c] for c in draws if c in credit}) for draws in (x, y)
            )
        items = [c for c, n in coeff.items() if n]
        total = len(items)
        if total > 32:
            items = [items[i] for i in rng.choice(total, 32, replace=False)]
        if not items:
            packet = None
        else:
            packet = pack(m, items, gate, "training", 0)
    if packet is None:
        return next(net.parameters()).sum() * 0, discovery / (2 * groups), slots, goal
    raw = log_paths(net, packet, np.arange(len(items)), "mps")
    scores = raw.clamp_min(1e-30).log().sum(1)
    scale = total / (len(items) * 2 * groups)
    w = scores.new_tensor([coeff[c] for c in items])
    return -(w * scores).sum() * scale, discovery / (2 * groups), slots, goal


def train(a):
    states = collect(a)
    bad = [read(f) for f in sorted((a.inputs / "failures").glob("*/page-*.pkl.gz"))]
    kinds = {k: [s for s in bad if k in s["kinds"]] for k in ("template", "binding")}
    focus = [
        s
        for s in kinds["binding"]
        if any(k == "binding" and r == 575 for k, (r, _) in zip(s["kinds"], s["rules"]))
    ]
    gate = weight(a).to("mps").eval()
    for seed in a.seeds:
        dest = a.out / "weights" / str(seed)
        dest.mkdir(parents=True, exist_ok=True)
        for ext in ("pt", "json"):
            shutil.copyfile(
                a.inputs / "weights" / str(seed) / f"original.{ext}",
                dest / f"original.{ext}",
            )
        for arm in ("coverage", "failure"):
            if (dest / f"{arm}.pt").exists():
                continue
            rng = np.random.default_rng(seed)
            sampling = np.random.default_rng(seed + 2)
            neg = np.random.default_rng(seed + 1)
            net = weight(a).to("mps")
            optimizer = torch.optim.AdamW(net.parameters(), lr=0.00015)
            hist = []
            for step in range(a.updates):
                m, g = states[rng.integers(len(states))]
                budget = int(rng.choice(BUDGETS))
                loss, distinct, slots, goal = coverage_gradient(
                    net, m, g, gate, budget, sampling
                )
                if arm == "failure":
                    k = "template" if step % 2 == 0 else "binding"
                    pool = focus if step % 4 == 3 else kinds[k]
                    loss = loss + reject_loss(net, pool[neg.integers(len(pool))], k)
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    net.parameters(), 5.0, error_if_nonfinite=True
                )
                optimizer.step()
                hist.append([budget, distinct, slots, goal])
            torch.save(net.cpu().state_dict(), dest / f"{arm}.pt")
            (dest / f"{arm}.json").write_text(json.dumps(hist) + "\n")
            print("trained", seed, arm, step + 1, flush=True)


@torch.no_grad()
def check_fit(a):
    """Paired train-set diagnostic restricted to the original certified alias bank."""
    frozen = collect(a)
    names = sorted((a.inputs / "examples").glob("*.pkl.gz"))
    rows = []
    params = {}
    for arm in ("original", "coverage", "failure"):
        net = weight(a)
        net.load_state_dict(
            torch.load(a.out / "weights" / "9633" / f"{arm}.pt", weights_only=True)
        )
        params[arm] = torch.cat([p.ravel() for p in net.parameters()]).to("mps")
    for (m, credit), name in zip(frozen, names, strict=True):
        r = int(name.name.split(".")[0].rsplit("-", 1)[1])
        domain = Domain(m)
        goal = min(256, domain.size)
        for draw in range(2):
            groups = {
                "factored": list(
                    domain.draw("factored", random.Random(seed_for(r, draw)), goal)
                )
            }
            for arm, param in params.items():
                items = []
                rng = np.random.default_rng(seed_for(r, draw))
                page = m.page
                page.weights[: len(param)].copy_(param)
                page.cap = 256
                for _ in range(1024):
                    if len(items) >= goal:
                        break
                    items.extend(v.cell for v in page.sample(m, (), 1, rng, Counter()))
                groups[arm] = items[:goal]
            for budget in BUDGETS:
                matched = min(budget, *(len(xs) for xs in groups.values()))
                for arm, xs in groups.items():
                    hit = {credit[c] for c in xs[:matched] if c in credit}
                    rows.append(
                        {
                            "state": name.name.split(".")[0],
                            "arm": arm,
                            "draw": draw,
                            "budget": budget,
                            "issued": matched,
                            "known_productive": len(hit),
                        }
                    )
    write_csv(a.out / "fit-check.csv", rows)


if __name__ == "__main__":
    from pathlib import Path

    p = cli()
    p.add_argument("--inputs", required=True, type=Path)
    p.add_argument("--updates", type=int, default=768)
    p.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    p.add_argument("--training-check", action="store_true")
    a = p.parse_args()
    torch.set_num_threads(1)
    (check_fit if a.training_check else train)(a)
    torch.mps.synchronize()
