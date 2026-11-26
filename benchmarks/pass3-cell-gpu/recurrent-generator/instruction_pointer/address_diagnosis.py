"""Enumerate one typed domain offline for ranks; never enumerate binding products."""

import gzip
import json

import numpy as np
import torch

from address_corpus import files, read_state
from address_scores import cluster, init_w, mlp, tree, weight
from parallel_budget import args

ARMS = (
    "original",
    "tree-dot",
    "direct-dot",
    "direct-old",
    "tree-fit",
    "tree-bilinear",
    "direct-fit",
)


def leaf_scores(q, k, tab, arm, net, w):
    mode = int(tab != -1)
    n = len(k)
    if n == 1:
        return np.ones((len(q), 1)), None
    li, ri, path, bits, mask, slices = tree(n)
    semantic = arm.startswith("semantic")
    flat = arm.startswith("direct")
    qq = torch.as_tensor(q, device="mps")
    kk = torch.as_tensor(k, device="mps")
    order = None
    if semantic:
        order, cent_left, cent_right = cluster(kk)
        kk = kk[order]
    if arm in ("original", "tree-fit", "direct-old", "direct-mlp", "semantic-mlp"):
        count = n if flat else n - 1
        chunks = []
        for offset in range(0, len(q) * count, 8192):
            p = torch.arange(offset, min(offset + 8192, len(q) * count), device="mps")
            v = qq[p // count]
            j = p % count
            if flat:
                key = kk[j]
                zero = torch.zeros_like(key)
                z = (mlp(net, v, zero, key, mode) - mlp(net, v, key, zero, mode)) * 0.5
            elif arm == "semantic-mlp":
                z = mlp(net, v, cent_left[j], cent_right[j], mode)
            else:
                l = torch.from_numpy(li).to("mps")
                r = torch.from_numpy(ri).to("mps")
                z = mlp(net, v, kk[l[j]], kk[r[j]], mode)
            chunks.append(z)
        z = torch.cat(chunks).reshape(len(q), count)
    elif semantic:
        sums = torch.cat((torch.zeros_like(kk[:1]), kk.cumsum(0)), 0)
        l, m, r = [torch.from_numpy(col.copy()).to("mps") for col in slices.T]
        diff = (sums[r] - sums[m]) / (r - m)[:, None] - (sums[m] - sums[l]) / (m - l)[
            :, None
        ]
        z = (qq @ w[mode]) @ diff.T
    else:
        allkeys = (qq @ w[mode]) @ kk.T
        z = allkeys if flat else allkeys[:, ri] - allkeys[:, li]
    if flat:
        return z.softmax(-1).cpu().numpy().astype(float), None
    branch = z.sigmoid().cpu().numpy().astype(float)
    # Depth-wise gather avoids a permanent queries x leaves x depth tensor.
    probs = np.ones((len(q), n))
    for j in range(path.shape[1]):
        v = branch[:, path[:, j]]
        probs *= np.where(mask[:, j], np.where(bits[:, j], v, 1 - v), 1)
    if semantic:
        probs = probs[:, np.argsort(order.cpu().numpy())]
    return probs, branch


def gates(q, rows, gate_net):
    ret = np.zeros((len(q), 2))
    for j in (0, 1):
        selected = [i for i, r in enumerate(rows) if (r[0] >= 0 if j == 0 else r[2])]
        if not selected:
            continue
        a = torch.from_numpy(np.stack([rows[i][3 + j] for i in selected])).to("mps")
        b = (
            torch.zeros_like(a)
            if not j
            else torch.from_numpy(np.stack([rows[i][5] for i in selected])).to("mps")
        )
        # For copy the Bernoulli success means bypass the copy.
        p = (
            mlp(gate_net, torch.as_tensor(q[selected], device="mps"), a, b, 2)
            .sigmoid()
            .cpu()
            .numpy()
        )
        ret[selected, j] = 1 - p if not j else p
    return ret


def route_trace(n, leaf, branches, i):
    if n <= 1 or branches is None or leaf < 0:
        return []
    _, _, paths, bits, mask, _ = tree(n)
    nodes = paths[leaf, mask[leaf]]
    right = bits[leaf, mask[leaf]]
    return np.where(right, branches[i, nodes], 1 - branches[i, nodes]).tolist()


@torch.no_grad()
def evaluate(a, arm):
    label = arm
    arm, _, feature = arm.partition("~")
    feature = feature or "queries"
    net = weight(a).to("mps").eval()
    gate = weight(a).to("mps").eval()
    if arm in ("tree-fit", "direct-mlp", "semantic-mlp"):
        net.load_state_dict(torch.load(a.out / (arm + ".pt"), weights_only=True))
    w = (
        torch.load(
            a.out / ("direct-fit.pt" if arm == "semantic-fit" else arm + ".pt"),
            weights_only=True,
        )
        if arm in ("direct-fit", "tree-bilinear", "semantic-fit")
        else init_w()
    ).to("mps")
    exp = []
    with gzip.open(a.out / f"paths-{label}.jsonl.gz", "wt", compresslevel=1) as out:
        for f in files(a, "eval"):
            s = read_state(f)
            groups = {}
            for tab, d in s["domains"].items():
                if not len(d["queries"]) or not len(d["keys"]):
                    continue
                prob, branches = leaf_scores(d[feature], d["keys"], tab, arm, net, w)
                g = gates(d[feature], d["gates"], gate)
                groups[tab] = (prob, branches, g, np.array(d["live"]))
            mass = []
            for r, refs, chain in s["tokens"]:
                steps = []
                tot = 1.0
                on = 0.0
                for j, (tab, i, y) in enumerate(chain):
                    if y < 0 or tab not in groups:
                        steps.append({"in_domain": False, "p": 0.0, "rank": None})
                        tot = 0.0
                        continue
                    bank, branches, g, live = groups[tab]
                    plain = bank[i]
                    c, proj, switch, *_ = s["domains"][tab]["gates"][i]
                    copy, group = g[i]
                    v = plain * (1 - copy)
                    if c >= 0:
                        v[c] += copy
                    if switch:
                        on = group
                    if proj != -2:
                        p_off = v[y]
                        v = v * (1 - on)
                        if proj >= 0:
                            v[proj] += on
                        post = on * int(proj == y)
                        denom = post + (1 - on) * p_off
                        on = post / denom if denom else 0.0
                    p = float(v[y])
                    rank = 1 + int(np.count_nonzero(v[live] > p))
                    row = {
                        "in_domain": True,
                        "p": p,
                        "rank": rank,
                        "ties": int(np.count_nonzero(v[live] == p)),
                        "domain": len(v),
                        "copy": float(copy),
                        "owner_selection": float(group),
                    }
                    if arm in ("original", "tree-fit", "tree-bilinear", "tree-dot"):
                        row["path"] = route_trace(len(v), y, branches, i)
                    steps.append(row)
                    tot *= p
                mass.append(tot)
                out.write(
                    json.dumps(
                        {
                            "case": s["case"],
                            "run": s["run"],
                            "rule": r,
                            "refs": refs,
                            "steps": steps,
                            "prob": tot,
                        }
                    )
                    + "\n"
                )
            mass = np.asarray(mass, dtype=float)
            exp.append(
                {
                    "case": s["case"],
                    "run": s["run"],
                    "known": len(mass),
                    "total_mass": mass.sum(),
                    "expected": {
                        n: float(
                            (-np.expm1(n * np.log1p(-mass.clip(0, 1 - 1e-16)))).sum()
                        )
                        for n in (4, 16, 64, 256)
                    },
                }
            )
    (a.out / f"expected-{label}.json").write_text(json.dumps(exp) + "\n")
    print(arm, len(exp), sum(v["expected"][256] for v in exp), flush=True)


if __name__ == "__main__":
    p = args()
    p.add_argument("--arms", nargs="+", default=ARMS)
    torch.set_num_threads(1)
    a = p.parse_args()
    for arm in a.arms:
        evaluate(a, arm)
