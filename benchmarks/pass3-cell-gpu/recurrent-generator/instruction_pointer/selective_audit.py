"""Strictly offline. Inspect every frozen pair, including competitors of the target root."""

from copy import copy
import numpy as np
import torch
from binding_model import read_packet
from first_parent import records
from joint_partner import model, batch, edge_view
from selective_worlds import args, path


@torch.no_grad()
def audit(a):
    old = copy(a)
    old.out = a.previous_joint
    dest = a.out / "pair-distributions"
    dest.mkdir(exist_ok=True)
    stats = []
    fits = []
    for seed in a.seeds:
        net = model(old, seed, "wide")
        for n in (32, 128, 256, 1024):
            for k in (0, 1):
                for f in (0, 1):
                    c = ("square", n, "two", 300001 + 8 * k, f)
                    z = read_packet(path(a, c) / "binding.pkl")
                    inp, w = batch([z])
                    edge = edge_view(inp, 0)
                    root, partner = z["gold"][0]
                    left, right = [
                        x[0].permute(1, 0, 2).contiguous()
                        for x in net.features(edge, w[0])
                    ]
                    prior = net.local.root_prior(inp)[0].cpu().numpy()
                    strength = net.local.strength.exp().item()
                    all_k = []
                    parts = {}

                    def add(name, arr):
                        parts.setdefault(name, []).append(arr)

                    def score(x):
                        return strength * (np.log(x + 1e-5) - np.log1p(x)).sum(-1)

                    for j in range(0, n, 64):
                        h = (left[:, j : j + 64] @ right.transpose(1, 2)).cpu().numpy()
                        value = h.mean(0)
                        all_k.append(value)
                        add("original", score(h.sum(2).T))
                        add("head-power4", score((h**4).sum(2).T))
                        for p in (1, 2, 4, 8):
                            add(
                                f"joint-sum-p{p}", 4 * score((value**p).sum(1)[:, None])
                            )
                        add("joint-max", 4 * score(value.max(1)[:, None]))
                        beta = 32
                        lse = np.log(np.exp(beta * value).mean(1)) / beta
                        add("joint-lse32", 4 * score(lse[:, None]))
                    K = np.concatenate(all_k)
                    np.savez_compressed(
                        dest / f"{seed}-{n}-{k}-{f}.npz",
                        kernel=K,
                        root=root,
                        partner=partner,
                    )
                    true = K[root, partner]
                    for scope, v in [
                        ("target-root", np.delete(K[root], partner)),
                        ("all", np.delete(K.ravel(), root * n + partner)),
                    ]:
                        sort = np.sort(v.astype(np.float64))
                        total = sort.sum()
                        stats.append(
                            dict(
                                seed=seed,
                                n=n,
                                k=k,
                                flip=f,
                                scope=scope,
                                count=len(v),
                                correct=true,
                                maximum=sort[-1],
                                gap=true - sort[-1],
                                mass=total,
                                p50=np.quantile(sort, 0.5),
                                p95=np.quantile(sort, 0.95),
                                p99=np.quantile(sort, 0.99),
                                top1_share=sort[-1] / total,
                                top8_share=sort[-8:].sum() / total,
                                ratio_above_half=np.mean(sort >= true * 0.5),
                                half_signal_share=sort[sort >= true * 0.5].sum()
                                / total,
                            )
                        )
                    for mode, v in parts.items():
                        logits = np.concatenate(v) + prior
                        prob = np.exp(logits - logits.max())
                        fits.append(
                            dict(
                                seed=seed,
                                n=n,
                                k=k,
                                flip=f,
                                mode=mode,
                                root=prob[root] / prob.sum(),
                                rank=1 + int((logits > logits[root]).sum()),
                                margin=logits[root] - np.delete(logits, root).max(),
                            )
                        )
        records(a.out / "kernel.csv", stats)
        records(a.out / "oracle-aggregation.csv", fits)
        print(seed, len(stats), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    audit(args())
