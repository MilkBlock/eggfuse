"""Conditional leaf probabilities for physical midpoint trees and per-role neural softmax."""

from functools import lru_cache

import numpy as np
import torch
from torch import nn

from address_corpus import files, read_state
from metal_scaling import models
from parallel_budget import args


@lru_cache(maxsize=128)
def tree(n):
    # node numbers index split decisions; gather one path per physical leaf.
    left = []
    right = []
    paths = [None] * n
    bits = [None] * n
    slices = []

    def split(lo, hi, path, b):
        if hi - lo == 1:
            paths[lo] = path
            bits[lo] = b
            return
        mid = (lo + hi) // 2
        j = len(left)
        left.append((lo + mid - 1) // 2)
        right.append((mid + hi - 1) // 2)
        slices.append((lo, mid, hi))
        split(lo, mid, path + [j], b + [False])
        split(mid, hi, path + [j], b + [True])

    split(0, n, [], [])
    h = max(map(len, paths))
    lengths = np.array(list(map(len, paths)))
    return (
        np.array(left, dtype=int),
        np.array(right, dtype=int),
        np.array([p + [0] * (h - len(p)) for p in paths], dtype=int),
        np.array([b + [False] * (h - len(b)) for b in bits], dtype=bool),
        np.arange(h) < lengths[:, None],
        np.array(slices, dtype=int),
    )


def mlp(net, q, k1, k2, mode):
    shape = q.shape[:-1]
    tail = q.new_zeros((*shape, 3))
    tail[..., mode] = 1
    return net(torch.cat((q, k1, k2, tail), dim=-1)).squeeze(-1)


def weight(a):
    net = models("1M")[0]
    net.load_state_dict(
        torch.load(a.previous / "s243/1M-n1000000/weights.pt", weights_only=True)[0]
    )
    return net.choice


def init_w():
    return torch.eye(32).repeat(2, 1, 1) / 32**0.5


def cluster(k):
    axis = torch.cos(torch.arange(32, device=k.device, dtype=k.dtype))
    order = (k @ axis).argsort(stable=True)
    sums = torch.cat((torch.zeros_like(k[:1]), k[order].cumsum(0)), 0)
    l, m, r = [torch.from_numpy(col.copy()).to(k.device) for col in tree(len(k))[-1].T]
    return (
        order,
        (sums[m] - sums[l]) / (m - l)[:, None],
        (sums[r] - sums[m]) / (r - m)[:, None],
    )


def train(a):
    rng = np.random.default_rng(9633)
    domains = []
    sizes = []
    for f in files(a, "train"):
        s = read_state(f)
        targets = {}
        for _, _, steps in s["tokens"]:
            for tab, i, y in steps:
                if y >= 0 and len(s["domains"][tab]["keys"]) > 1:
                    targets.setdefault(tab, []).append((i, y))
        for tab, pairs in targets.items():
            d = s["domains"][tab]
            k = torch.from_numpy(d["keys"])
            q = torch.from_numpy(d["queries"])
            domains.append((int(tab != -1), k, q, np.array(pairs)))
            sizes.append(len(pairs))
    schedule = []
    for j in rng.choice(len(sizes), a.updates, p=np.array(sizes) / sum(sizes)):
        schedule.append((j, rng.integers(len(domains[j][3]), size=32)))
    import json

    log = {}
    for arm in a.arms:
        net = weight(a).to("mps")
        w = nn.Parameter(init_w().to("mps"))
        optim = torch.optim.AdamW(
            net.parameters()
            if arm in ("tree-fit", "direct-mlp", "semantic-mlp")
            else [w],
            lr=0.00025 if arm in ("tree-fit", "direct-mlp", "semantic-mlp") else 0.012,
        )
        losses = []
        clusters = {}
        for j, sel in schedule:
            mode, k, q, pairs = domains[j]
            qi, y = pairs[sel].T
            q = q[qi].to("mps")
            k = k.to("mps")
            if arm == "direct-mlp":
                # Limit training activation memory; every endpoint still uses its entire role denominator.
                optim.zero_grad()
                batchloss = 0
                for chunk in range(0, len(q), max(1, 1024 // len(k))):
                    take = max(1, 1024 // len(k))
                    qs = q[chunk : chunk + take]
                    u = qs[:, None, :].expand(-1, len(k), -1)
                    v = k.expand(len(qs), -1, -1)
                    zero = torch.zeros_like(v)
                    logits = 0.5 * (
                        mlp(net, u, zero, v, mode) - mlp(net, u, v, zero, mode)
                    )
                    part = nn.functional.cross_entropy(
                        logits,
                        torch.from_numpy(y[chunk : chunk + take].copy()).to("mps"),
                        reduction="sum",
                    ) / len(y)
                    part.backward()
                    batchloss = batchloss + part.detach()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 5)
                optim.step()
                losses.append(batchloss)
                continue
            elif arm == "direct-fit":
                loss = nn.functional.cross_entropy(
                    (q @ w[mode]) @ k.T, torch.from_numpy(y.copy()).to("mps")
                )
            else:
                li, ri, path, bits, mask, _ = tree(len(k))
                if arm == "semantic-mlp":
                    if j not in clusters:
                        order, left, right = cluster(k)
                        clusters[j] = (order.argsort().cpu().numpy(), left, right)
                    inv, left, right = clusters[j]
                    y = inv[y]
                node = path[y][mask[y]]
                idx = np.nonzero(mask[y])[0]
                akey = k[li[node]]
                bkey = k[ri[node]]
                if arm == "semantic-mlp":
                    akey, bkey = left[node], right[node]
                qq = q[idx]
                logits = (
                    mlp(net, qq, akey, bkey, mode)
                    if arm in ("tree-fit", "semantic-mlp")
                    else ((qq @ w[mode]) * (bkey - akey)).sum(-1)
                )
                labels = torch.from_numpy(bits[y][mask[y]].astype("float32")).to("mps")
                loss = nn.functional.binary_cross_entropy_with_logits(
                    logits, labels, reduction="sum"
                ) / len(y)
            optim.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                net.parameters()
                if arm in ("tree-fit", "direct-mlp", "semantic-mlp")
                else [w],
                5,
            )
            optim.step()
            losses.append(loss.detach())
        vals = torch.stack(losses).cpu().tolist()
        log[arm] = [float(np.mean(v)) for v in np.array_split(vals, 4)]
        torch.save(
            net.cpu().state_dict()
            if arm in ("direct-mlp", "tree-fit", "semantic-mlp")
            else w.detach().cpu(),
            a.out / f"{arm}.pt",
        )
        print(arm, log[arm], flush=True)
    for arm, values in log.items():
        (a.out / ("loss-" + arm + ".json")).write_text(json.dumps(values) + "\n")


if __name__ == "__main__":
    p = args()
    p.add_argument("--updates", type=int, default=1600)
    p.add_argument(
        "--arms",
        nargs="+",
        default=["tree-fit", "tree-bilinear", "direct-fit", "direct-mlp"],
    )
    torch.set_num_threads(1)
    train(p.parse_args())
