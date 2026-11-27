"""Device-resident diagnostic for root summaries. Synchronization is explicit here only."""

from statistics import median
from time import perf_counter
import torch
from binding_model import collate, read_packet
from first_parent import load, options, records


@torch.no_grad()
def measure(a):
    net = load(a, 9633, "pool")
    rows = []
    for n in (4, 8, 16, 32, 64, 128, 256, 1024):
        for i in (20000, 20001, 20002):
            d = a.previous_binding / "worlds/test" / f"{n:04}-eq10-{i}-0"
            z = read_packet(d / "binding.pkl")
            inp = collate([z])
            roots = sorted({q[0] for q in z["gold"]})
            others = sorted(set(range(n)) - set(roots))
            for mode in ("pool", "dense"):
                if mode == "dense" and n > 32:
                    continue
                ids = torch.arange(n, device="mps")[None]

                def scores():
                    if mode == "pool":
                        return net.pool_scores(inp)
                    return net.relation(inp, ids).logsumexp(-1)

                v = scores()[0]
                torch.mps.synchronize()
                times = []
                for _ in range(7):
                    t = perf_counter()
                    for _ in range(5):
                        scores()
                    torch.mps.synchronize()
                    times.append((perf_counter() - t) * 200)
                cols = inp[3][0][1].shape[2]
                rows.append(
                    dict(
                        size=n,
                        instance=i,
                        mode=mode,
                        root_rows=n,
                        right_rows=n,
                        field_width=cols,
                        root_pair_scores=n * n if mode == "dense" else 0,
                        soft_assignment_logits=2 * n * cols * 4 * 128
                        if mode == "pool"
                        else 0,
                        median_ms=median(times),
                        min_ms=min(times),
                        max_ms=max(times),
                        best_vs_best_gap=float(v[roots].max() - v[others].max()),
                        mean_gap=float(v[roots].mean() - v[others].mean()),
                    )
                )
    records(a.out / "root-cost.csv", rows)


if __name__ == "__main__":
    a = options().parse_args()
    torch.set_num_threads(1)
    measure(a)
