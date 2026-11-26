"""Time device-resident address selection as the single typed domain grows."""

import json
from time import perf_counter

import torch

from address_corpus import files, read_state
from address_scores import cluster, mlp, weight
from parallel_budget import args


@torch.no_grad()
def run(a):
    net = weight(a).to("mps")
    sd = torch.load(a.out / "direct-mlp.pt", weights_only=True)
    net.load_state_dict(sd)
    tree_net = weight(a).to("mps")
    tree_net.load_state_dict(torch.load(a.out / "tree-fit.pt", weights_only=True))
    bilinear = torch.load(a.out / "direct-fit.pt", weights_only=True).to("mps")[1]
    source = None
    for f in files(a, "eval"):
        for tab, d in read_state(f)["domains"].items():
            if tab >= 0 and (source is None or len(d["keys"]) > len(source["keys"])):
                source = d
    k = torch.from_numpy(source["keys"]).to("mps")
    q = torch.from_numpy(source["queries"]).to("mps")
    rows = []
    for n in (64, 256, 1024, len(k)):
        bank = k[:n]
        for bs in (1, 16, 64):
            qs = q[torch.arange(bs, device="mps") % len(q)]

            def bench(arm, bank=bank, bs=bs, n=n, qs=qs):
                if arm == "semantic_rebuild":
                    return cluster(bank)
                if arm == "tree":
                    lo = torch.zeros(bs, dtype=torch.int64, device="mps")
                    hi = torch.full_like(lo, n)
                    for _ in range((n - 1).bit_length()):
                        mid = (lo + hi) // 2
                        logits = mlp(
                            tree_net,
                            qs,
                            bank[((lo + mid - 1) // 2).clamp_min(0)],
                            bank[(mid + hi - 1) // 2],
                            1,
                        )
                        right = torch.rand(bs, device="mps") < logits.sigmoid()
                        active = hi - lo > 1
                        lo, hi = (
                            torch.where(active & right, mid, lo),
                            torch.where(active & ~right, mid, hi),
                        )
                    return lo
                if arm == "bilinear":
                    logits = (qs @ bilinear) @ bank.T
                else:
                    blocks = []
                    for chunk in bank.split(max(1, 2048 // bs)):
                        v = chunk.expand(bs, -1, -1)
                        u = qs[:, None, :].expand_as(v)
                        zero = torch.zeros_like(v)
                        blocks.append(
                            0.5 * (mlp(net, u, zero, v, 1) - mlp(net, u, v, zero, 1))
                        )
                    logits = torch.cat(blocks, 1)
                u = torch.rand_like(logits).clamp_(1e-7, 1 - 1e-7)
                return (logits - u.log().neg().log()).argmax(-1)

            arms = ["tree", "bilinear", "dense_mlp"] + (
                ["semantic_rebuild"] if bs == 1 else []
            )
            for arm in arms:
                bench(arm)
            torch.mps.synchronize()
            for rep in range(3):
                for arm in arms if rep % 2 == 0 else reversed(arms):
                    start = perf_counter()
                    for _ in range(4):
                        bench(arm)
                    torch.mps.synchronize()
                    duration = (perf_counter() - start) / 4
                    rows.append(
                        {
                            "domain": n,
                            "batch": bs,
                            "arm": arm,
                            "rep": rep,
                            "seconds": duration,
                            "queries_per_second": bs / duration
                            if arm != "semantic_rebuild"
                            else None,
                        }
                    )
    (a.out / "growth.json").write_text(json.dumps(rows) + "\n")


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args().parse_args())
