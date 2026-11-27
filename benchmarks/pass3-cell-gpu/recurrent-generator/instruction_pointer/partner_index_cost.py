"""Device synchronized page, sparse posting maintenance, and actual partner reads."""

import numpy as np
import torch
from binding_model import tensor, read_packet, bit_lanes
from first_parent import records
from joint_partner_cost import timed, growing
from selective_replication import AllocationTrace
from selective_kernel import build_index
from joint_partner import align
from selective_trials import inputs
from partner_index import prepare, draw, noise
from partner_index_worlds import args, folder, frozen


def bytes_in(obj):
    return sum(t.element_size() * t.numel() for t in obj)


@torch.no_grad()
def measure(a):
    m = frozen(a, 9633)
    costs = []
    updates = []
    for n in (1024, 8192, 32768):
        z = read_packet(folder(a, ("hard", n, 511000, 0)) / "binding.pkl")
        data = inputs(z, False)
        u = noise(np.random.default_rng(33), 32, 2)
        upload = timed(lambda: inputs(z, False))
        for arm in ("legacy", "linear", "refined", "shared-score"):

            def build():
                return (m.flow(*data), None) if arm == "legacy" else prepare(m, data)

            def full():
                return draw(m, data, build(), u, arm)

            state = build()
            dec = timed(lambda: draw(m, data, state, u, arm))
            build_ms = timed(build)
            page = timed(full)
            torch.mps.synchronize()
            with AllocationTrace() as mem:
                ix, used = full()
            torch.mps.synchronize()
            if used:
                union = torch.cat((ix[:, :, 1], used[0].flatten(1)), dim=1)
                unique = int(union.unique().numel())
                postings = used[0].numel()
                index_bytes = bytes_in(state[1][0].index)
            else:
                unique = n
                postings = 0
                index_bytes = 0
            costs.append(
                dict(
                    n=n,
                    arm=arm,
                    pack_ms=upload,
                    build_ms=build_ms,
                    decode_ms=dec,
                    page_ms=page,
                    observed_peak_bytes=mem.peak - mem.initial,
                    dispatches=mem.calls,
                    owner_ordinal_reads=postings,
                    unique_partners=unique,
                    neural_pair_scores=32 * n
                    if arm == "legacy"
                    else 256
                    if arm in ("refined", "shared-score")
                    else 0,
                    named_index_bytes=index_bytes,
                    final_partner_resolutions=32,
                )
            )
        records(a.out / "cost.csv", costs)
        for delta in (1, 32):
            z, changed = growing(a, n, delta)
            inp, edges = inputs(z, False)
            cols = edges[0][1][:, :, 1]
            whole = inp[3][1][1]
            sel = tensor(np.array(changed))
            small = whole[:, sel]
            for fixed in (False, True):

                def encode(x):
                    return m.mapping(align(x, cols), m.variant, fixed_order=fixed)

                def index(x, origin=None):
                    v = encode(x)
                    idx = build_index(v, x.new_ones(x.shape[:2]), named=True)
                    if origin is None:
                        return idx
                    return idx[0], idx[1], origin[idx[2].long()].int()

                seg = index(small, sel)
                ref = index(whole)
                fullcode = encode(whole)
                segmentcode = encode(small)
                # Verify backpointers against the encoding that built each index.
                joined = fullcode[0].clone()
                joined[:, :, sel] = segmentcode[0]
                for idx, ids in ((seg, joined), (ref, fullcode[0])):
                    for h in range(ids.size(1)):
                        vals = ids[0, h, idx[2][0, h].long()]
                        assert bool((vals == idx[0][0, h, :, None]).any(1).all())
                disagreement = int(
                    (fullcode[0][:, :, sel, 0] != segmentcode[0][..., 0]).sum()
                )
                error = float(
                    (
                        (fullcode[0][:, :, sel, 0] + fullcode[1][:, :, sel, 1])
                        - (segmentcode[0][..., 0] + segmentcode[1][..., 1])
                    )
                    .abs()
                    .max()
                )
                if fixed:
                    assert disagreement == 0 and error == 0
                updates.append(
                    dict(
                        n=n,
                        delta=delta,
                        projection="fixed" if fixed else "original",
                        differing_coordinates=disagreement,
                        max_bin_position_error=error,
                        full_ms=timed(lambda: index(whole)),
                        segment_ms=timed(lambda: index(small, sel)),
                        pack_segment_ms=timed(
                            lambda: index(
                                tensor(bit_lanes(z["banks"][1]["hash"][changed][None])),
                                sel,
                            )
                        ),
                        full_bytes=bytes_in(ref),
                        segment_bytes=bytes_in(seg),
                    )
                )
        records(a.out / "updates.csv", updates)
        print("cost", n, flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    measure(args())
