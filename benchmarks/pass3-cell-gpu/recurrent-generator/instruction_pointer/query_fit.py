"""Matched training on full signed bindings, marginalizing only native-verified alternatives."""

import csv
import gzip
import json
import pickle
from functools import lru_cache

import numpy as np
import torch
from torch.nn import functional as F

from address_scores import weight
from query_witnesses import arguments


@lru_cache(maxsize=10)
def read(path):
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


def log_paths(net, state, indices, device):
    route = state["paths"][indices]
    unique, inverse = np.unique(abs(route), return_inverse=True)
    features = torch.from_numpy(state["features"][unique]).to(device)
    logits = net(features).flatten()[
        torch.as_tensor(inverse.reshape(route.shape), device=device)
    ]
    sign = torch.as_tensor(np.sign(route), device=device)
    base = F.logsigmoid(logits * sign).masked_fill(sign == 0, 0.0).sum(-1).exp()
    meta = torch.from_numpy(state["meta"][indices]).to(device)
    on = torch.zeros_like(base[:, 0])
    parts = []
    for j in range(base.shape[1]):
        copy, copyhit, switch, project, projecthit, present, domain = meta[:, j].unbind(
            -1
        )
        plain = (1 - copy) * base[:, j] + copy * copyhit
        on = torch.where(switch >= 0, switch, on)
        combined = on * projecthit + (1 - on) * plain
        p = torch.where(project.bool(), combined, plain) * domain
        on = torch.where(
            project.bool(), on * projecthit / combined.clamp_min(1e-30), on
        )
        parts.append(torch.where(present.bool(), p, 1.0))
    return torch.stack(parts, 1)


def batch(net, s, groups, device):
    offsets = s["offsets"]
    sizes = offsets[groups + 1] - offsets[groups]
    cols = np.arange(max(sizes))
    valid = cols[None, :] < sizes[:, None]
    idx = offsets[groups, None] + cols
    factors = log_paths(net, s, idx[valid], device)
    token_log = factors.clamp_min(1e-30).log().sum(-1)
    mapping = valid.cumsum().reshape(valid.shape) - 1
    matrix = token_log[torch.from_numpy(mapping).to(device)].masked_fill(
        ~torch.from_numpy(valid).to(device), float("-inf")
    )
    primary = np.r_[0, np.cumsum(sizes)[:-1]]
    return matrix, factors[torch.from_numpy(primary).to(device)]


def output(a):
    dest = a.out / "crossfit" / a.holdout if a.holdout else a.out
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def fit(a):
    history = {}
    for arm in a.arms:
        env = "env" if arm in ("B", "D") else "old"
        files = sorted((a.out / "train" / env).glob("*.pkl.gz"))
        if len(files) != 108:
            raise ValueError(f"incomplete training split: {len(files)}")
        if a.holdout:
            files.extend(
                sorted(
                    f
                    for f in (a.out / "eval" / env).glob("*.pkl.gz")
                    if f.name.split("-teacher-")[0]
                    in {"fact", "loopfact", "sum-divisors"} - {a.holdout}
                )
            )
        net = weight(a).to("mps")
        opt = torch.optim.AdamW(net.parameters(), lr=0.00015)
        rng = np.random.default_rng(9633)
        # Each distinct signed binding contributes a separate loss, even when
        # its witnessed alternative addresses have higher probability.
        states = [read(f) for f in files]
        sizes = np.array([len(s["gains"]) for s in states])
        losses = []
        for _ in range(a.updates):
            s = states[rng.choice(len(states), p=sizes / sizes.sum())]
            chosen = rng.integers(len(s["gains"]), size=32)
            matrix, _ = batch(net, s, chosen, "mps")
            loss = -(matrix.logsumexp(1) if arm in ("C", "D") else matrix[:, 0]).mean()
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0)
            opt.step()
            losses.append(float(loss.detach().cpu()))
        torch.save(net.cpu().state_dict(), output(a) / f"{arm}.pt")
        history[arm] = dict(
            updates=a.updates,
            seed=9633,
            states=len(files),
            groups=int(sum(sizes)),
            loss=losses,
            parameters=sum(p.numel() for p in net.parameters()),
        )
        (output(a) / "fit.json").write_text(json.dumps(history) + "\n")
        print(arm, np.mean(losses[:32]), np.mean(losses[-32:]), flush=True)


@torch.no_grad()
def evaluate(a):
    for arm in a.arms:
        net = weight(a).to("mps").eval()
        net.load_state_dict(torch.load(output(a) / f"{arm}.pt", weights_only=True))
        files = sorted(
            (a.out / "eval" / ("env" if arm in ("B", "D") else "old")).glob("*.pkl.gz")
        )
        if len(files) != 109:
            raise ValueError(f"incomplete evaluation split: {len(files)}")
        if a.holdout:
            files = [f for f in files if f.name.split("-teacher-")[0] == a.holdout]
        with gzip.open(output(a) / f"prob-{arm}.csv.gz", "wt") as out:
            w = csv.writer(out)
            w.writerow(
                "case run group gain p_template p_first p_later p_exact p_class p_binding_class p_parents".split()
            )
            for f in files:
                case, run = f.name.split("-teacher-")
                s = read(f)
                for chunk in np.array_split(
                    np.arange(len(s["gains"])), max(1, (len(s["gains"]) + 31) // 32)
                ):
                    l, p = batch(net, s, chunk, "mps")
                    exact = l[:, 0].exp().cpu().numpy()
                    equiv = l.logsumexp(1).exp().cpu().numpy()
                    probs = p.cpu().numpy()
                    for i, j in enumerate(chunk):
                        n = int(s["meta"][s["offsets"][j], :, 5].sum())
                        row = probs[i, :n]
                        w.writerow(
                            [
                                case,
                                int(run.split(".")[0]),
                                j,
                                s["gains"][j],
                                row[0],
                                row[1] if n > 1 else "",
                                row[2:].mean() if n > 2 else "",
                                exact[i],
                                equiv[i],
                                equiv[i] / max(row[0], 1e-30),
                                json.dumps(row[1:].tolist()),
                            ]
                        )


if __name__ == "__main__":
    p = arguments()
    p.add_argument("mode", choices=["fit", "eval"])
    p.add_argument("--updates", type=int, default=768)
    p.add_argument("--arms", nargs="+", default=list("ABCD"))
    p.add_argument("--holdout", choices=["fact", "loopfact", "sum-divisors"])
    a = p.parse_args()
    torch.set_num_threads(1)
    (fit if a.mode == "fit" else evaluate)(a)
