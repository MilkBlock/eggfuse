"""Offline adversarial fixture construction. Only compiled public rows reach inference."""

import numpy as np
import torch

import head_joint_index as joint
import partner_index as old
from binding_model import read_packet
from binding_packets import packet
from binding_worlds import build
from first_parent import records
from head_joint_audit import overlaps
from head_joint_worlds import suite
from partner_index_worlds import args, frozen
from selective_trials import inputs


@torch.no_grad()
def run(a):
    n = 32768
    seed = 9633
    m = frozen(a, seed)
    base = next(
        d for size, v, f, den, i, d in suite(a) if (size, v, f, den) == (n, 1, 0, 1.0)
    )
    z = read_packet(base / "binding.pkl")
    data = inputs(z, False)
    future, edges = old.prepare(m, data)
    e = edges[0]
    roots, k = overlaps(e.query, e.partner)
    separate = np.zeros((n, 4), bool)
    simultaneous = np.zeros(n, bool)
    np.logical_or.at(separate, roots, k > 0)
    np.logical_or.at(simultaneous, roots, (k > 0).all(1))
    rivals = separate.all(1) & ~simultaneous
    # Use a strong old-readout false root and an unsupported control from the same world.
    score = future[0][0].cpu().numpy()
    lure = z["banks"][0]["raw"][np.where(rivals, score, -np.inf).argmax(), :3]
    neutral = z["banks"][0]["raw"][np.flatnonzero(~separate.any(1))[0], :3]
    target = z["banks"][0]["raw"][z["gold"][0][0], :3]
    column = next(i for i, s in enumerate(z["slots"][0]) if s not in z["slots"][1])
    results = []
    for pct in (0, 25, 75):
        case = f"lure-{pct}"
        d = a.out / "worlds" / case / "32768-two-511000-0"
        if not (d / "ok.json").exists():
            lines = []
            row = 0
            for line in (base / "world.egg").read_text().splitlines():
                if line.startswith("(Left "):
                    raw = tuple(map(int, line[6:-1].split()))
                    if raw != tuple(target):
                        vals = list(lure if row % 100 < pct else neutral)
                        vals[column] = 2**61 + row
                        line = "(Left " + " ".join(map(str, vals)) + ")"
                        row += 1
                lines.append(line)
            assert row == n - 1
            build(
                a,
                (case, 511000, n, "two", 0, False, False),
                override="\n".join(lines) + "\n",
            )
        packet(a, d)
        probe = read_packet(d / "binding.pkl")
        assert len(probe["gold"]) == 1
        root = probe["gold"][0][0]
        inp = inputs(probe, False)
        fut, edges = old.prepare(m, inp)
        p = (m.local.root_prior(inp[0]) + fut[0])[0].softmax(-1)
        prob, links = joint.prepare(m, inp)
        # Count actual distributed-root supports with the device indices.
        from selective_kernel import read_index

        spread = (read_index(edges[0].query, edges[0].index[:2]) > 0).all(-1)
        mass = links[0].mass.sum(-1)
        results.append(
            {
                "pct": pct,
                "n": n,
                "distributed": int((spread & (mass == 0)).sum()),
                "old_rank": int((p > p[root]).sum()) + 1,
                "old_prob": float(p[root]),
                "new_rank": int((prob > prob[0, root]).sum()) + 1,
                "new_prob": float(prob[0, root]),
            }
        )
        records(a.out / "lures.csv", results)
        print(results[-1], flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
