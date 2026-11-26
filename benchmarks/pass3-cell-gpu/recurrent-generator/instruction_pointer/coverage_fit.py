"""Change the objective of the existing address MLP; all other generator weights stay frozen."""

import json

import numpy as np
import torch

from address_scores import weight
from discovery_states import cli
from query_fit import log_paths, read

BUDGETS = (4, 16, 64, 256)
ARMS = ("original", "coverage", "failure")
SEEDS = (9633, 5003, 1777)


def expected_distinct(p, budget):
    # Integer powers have a finite gradient even for p=1. For tiny probabilities,
    # log1p/expm1 avoids cancellation; mask the endpoint before taking the log.
    if budget == 1:
        return p
    safe = torch.where(p >= 1, 0.0, p)
    return torch.where(
        p >= 1, torch.ones_like(p), -torch.expm1(budget * torch.log1p(-safe))
    )


def probability(net, state):
    return log_paths(net, state, np.arange(len(state["paths"])), "mps")


def objective(net, state, arm, budget):
    ids = torch.as_tensor(state["signature"], device="mps", dtype=torch.long)
    n = len(ids)
    probs = probability(net, state).prod(1)
    mass = probs.new_zeros(len(state["gains"]))
    if arm == "original":
        orig = torch.as_tensor(state["original"], device="mps")
        mass = mass.scatter_add(0, ids, probs[:n] * orig)
        return -mass.clamp_min(1e-30).log().mean()
    mass = mass.scatter_add(0, ids, probs[:n])
    weights = torch.from_numpy(state["importance"]).to("mps")
    z = probs[:n].sum() + (probs[n:] * weights).sum()
    positive = torch.from_numpy(state["gains"] > 0).to("mps")
    p = (mass / z.clamp_min(1e-30)).clamp(max=1)
    # Nonproductive and unknown are included only in the complete-token partition.
    return -(expected_distinct(p, budget) * positive).sum()


def reject_loss(net, state, kind):
    idx = [i for i, k in enumerate(state["kinds"]) if k == kind]
    if kind == "template":
        # A confirmed dirty refusal labels the template in this exact context.
        distinct = {state["rules"][i]: i for i in idx}
        factors = log_paths(net, state, np.array(list(distinct.values())), "mps")
        p = factors[:, 0].sum()
    else:
        # Penalize the specific witnessed wrong binding given its template,
        # preserving legal alternatives of that rule. Count repeated cells once.
        factors = log_paths(net, state, np.array(idx), "mps")
        by_rule = {}
        for j, i in enumerate(idx):
            by_rule.setdefault(state["rules"][i], []).append(j)
        p = torch.stack(
            [factors[js, 1:].prod(1).sum() for js in by_rule.values()]
        ).mean()
    return -torch.log1p(-p.clamp(max=1 - 1e-6))


def train(a):
    files = sorted((a.out / "examples").glob("*.pkl.gz"))
    if len(files) != 108:
        raise ValueError(f"expected 108 training states, found {len(files)}")
    states = [read(f) for f in files]
    bad = [read(f) for f in sorted((a.out / "failures").glob("*/page-*.pkl.gz"))]
    kinds = {k: [s for s in bad if k in s["kinds"]] for k in ("template", "binding")}
    focus = [
        s
        for s in kinds["binding"]
        if any(k == "binding" and r == 575 for k, (r, _) in zip(s["kinds"], s["rules"]))
    ]
    if not focus or not kinds["template"]:
        raise ValueError("missing verified failure strata")
    for seed in a.seeds:
        for arm in ARMS:
            dest = a.out / "weights" / str(seed)
            dest.mkdir(parents=True, exist_ok=True)
            if (dest / f"{arm}.pt").exists():
                continue
            net = weight(a).to("mps")
            optimizer = torch.optim.AdamW(net.parameters(), lr=0.00015)
            rng, neg = np.random.default_rng(seed), np.random.default_rng(seed + 1)
            history = []
            for step in range(a.updates):
                s = states[rng.integers(len(states))]
                budget = int(rng.choice(BUDGETS))
                loss = objective(net, s, arm, budget)
                if arm == "failure":
                    kind = "template" if step % 2 == 0 else "binding"
                    pool = focus if step % 4 == 3 else kinds[kind]
                    loss = loss + reject_loss(net, pool[neg.integers(len(pool))], kind)
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    net.parameters(), 5.0, error_if_nonfinite=True
                )
                optimizer.step()
                history.append(float(loss.detach().cpu()))
            (dest / f"{arm}.json").write_text(json.dumps(history) + "\n")
            torch.save(net.cpu().state_dict(), dest / f"{arm}.pt")
            print(seed, arm, np.mean(history[:64]), np.mean(history[-64:]), flush=True)


if __name__ == "__main__":
    p = cli()
    p.add_argument("--updates", type=int, default=768)
    p.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    a = p.parse_args()
    torch.set_num_threads(1)
    train(a)
    torch.mps.synchronize()
