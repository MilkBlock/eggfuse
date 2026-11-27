"""Synchronized GPU stage costs and append/rebuild from real native publications."""

import numpy as np
import torch
from binding_model import read_packet, tensor, bit_lanes
from first_parent import records
from joint_partner_cost import timed, growing
from selective_kernel import ARMS, net, read_index, pack
from selective_worlds import args, path


def storage(t):
    if isinstance(t, tuple):
        return sum(map(storage, t))
    return t.numel() * t.element_size()


@torch.no_grad()
def run(a):
    models = {arm: net(a, 9633, arm) for arm in ARMS}
    rows = []
    for n in (32, 128, 256, 1024, 4096, 8192):
        z = read_packet(path(a, ("square", n, "two", 300001, 0)) / "binding.pkl")
        data = pack([z])
        inp, edges = data
        x, y = [b[1] for b in inp[3]]
        cols = edges[0][1]
        upload = timed(lambda: pack([z]))
        noise = tensor(
            np.random.default_rng(9633).random((1, 32, 2)).astype(np.float32)
        )
        for arm, m in models.items():
            future = m.flow(*data)
            w = torch.ones_like(future[1])
            L = m.encode(x, cols[:, :, 0])
            R = m.encode(y, cols[:, :, 1])
            idx = m.summarize(R, w)
            row = dict(
                n=n,
                arm=arm,
                upload_ms=upload,
                encode_right_ms=timed(lambda: m.encode(y, cols[:, :, 1])),
                build_index_ms=timed(lambda: m.summarize(R, w)),
                query_ms=timed(lambda: m.evidence_from(L, idx)),
                messages_ms=timed(lambda: m.flow(*data)),
                decode32_ms=timed(lambda: m.draw(data, future, None, noise)),
                forward32_ms=timed(lambda: m(data, noise=noise)),
                right_feature_bytes=storage(R),
                index_bytes=storage(idx),
                conditional_scores=32 * n,
                query_insertion_points=4 * L[0].size(1) * n
                if isinstance(L, tuple)
                else 0,
            )
            rows.append(row)
        records(a.out / "cost.csv", rows)
    updates = []
    for n in (1024, 4096, 8192):
        for delta in (1, 8, 32):
            z, ix = growing(a, n, delta)
            inp, edges = pack([z])
            cols = edges[0][1]
            right = inp[3][1][1]
            new = right[:, tensor(np.array(ix))]
            old = right[:, tensor(np.delete(np.arange(n), ix))]
            for arm in ("wide", "joint-sparse", "mixed-sparse"):
                m = models[arm]

                def idx(x):
                    return m.summarize(
                        m.encode(x, cols[:, :, 1]), x.new_ones(x.shape[:2])
                    )

                q = m.encode(inp[3][0][1], cols[:, :, 0])
                base = idx(old)
                upd = idx(new)
                full = idx(right)

                def read(index):
                    if isinstance(index, tuple):
                        return read_index(q, index)
                    return torch.einsum("bnhk,bhk->bnh", q, index)

                split = read(base) + read(upd)
                whole = read(full)
                torch.testing.assert_close(split, whole, atol=2e-4, rtol=1e-4)
                updates.append(
                    dict(
                        n=n,
                        delta=delta,
                        arm=arm,
                        add_segment_ms=timed(lambda: idx(new)),
                        pack_add_ms=timed(
                            lambda: idx(
                                tensor(bit_lanes(z["banks"][1]["hash"][ix][None]))
                            )
                        ),
                        read_split_ms=timed(lambda: read(base) + read(upd)),
                        read_full_ms=timed(lambda: read(full)),
                        compact_full_ms=timed(lambda: idx(right)),
                        live_roots=q[0].shape[2]
                        if isinstance(q, tuple)
                        else q.shape[1],
                        error=(split - whole).abs().max().item(),
                    )
                )
        records(a.out / "updates.csv", updates)
        print(n, "updates", flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
