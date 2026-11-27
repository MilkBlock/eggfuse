"""Offline information audit with the native gold Seed supplied; never used for generation."""

import math
from itertools import product

import torch

from cell_kv_model import public_values
from cell_kv_runtime import native
from partner_index_worlds import args
from token_embedding import TokenEmbedding
from token_embedding_study import SEEDS, held, initial, save, weights


def agrees_on_overlap(row):
    # A three-field projection has eight distinct signed sums per lane.
    # Only 25 physical bits overlap between the first and shifted second fields.
    signs = torch.tensor(list(product((-1.0, 1.0), repeat=3)), dtype=row.dtype)
    levels = signs @ torch.tensor([1.0, 0.5, 1 / 3], dtype=row.dtype)
    decoded = signs[(row[:, None] - levels).abs().argmin(1)]
    return torch.equal(decoded[7:, 0], decoded[:25, 1])


@torch.no_grad()
def run(a):
    rows = []
    for w in held(a):
        s, targets = native(a, w, teacher="higher")[0]
        for seed in SEEDS:
            net = TokenEmbedding(a, "current", initial()).eval()
            net.load_state_dict(
                torch.load(weights(a, "current", seed), weights_only=True)
            )
            net.prepare(w)
            types = net.cache[2]
            m = net.state(w, s)
            for tid, refs in targets:
                if tid < w.primitives:
                    continue
                i = m["pos"][refs[0]]
                ref, owner, src, tab, fields, fwd, parents = s["ports"][i]
                assert src == -1 and not parents and len(fields) == 3
                expected = tid == w.primitives  # First baked body is L, guard x=y.
                raw = public_values([fields])[0]
                g = int(m["group"][i])
                assert len(m["siblings"][g]) == 1

                # Invert this specific singleton, fresh initial instance only.
                def atanh(x):
                    return torch.atanh(x.clamp(-1 + 1e-7, 1 - 1e-7))

                h = torch.linalg.solve(
                    net.actor.input_content.weight.double(), m["keys"][g].double()
                )
                val = atanh(h) - types[tab].double()
                age = torch.tensor(
                    [math.log1p(max(0, s["epoch"] - ref[2])) / 8, float(fwd)]
                )
                dense = atanh(val) - types[tab].double() - net.actor.age(age).double()
                recovered = torch.linalg.solve(net.actor.dynamic.weight.double(), dense)
                rows.append(
                    {
                        "case": w.dir.name,
                        "seed": seed,
                        "owner": owner,
                        "expected": expected,
                        "hashes_equal": fields[0] == fields[1],
                        "row_agrees": agrees_on_overlap(raw),
                        "key_agrees": agrees_on_overlap(recovered),
                        "recovery_max_error": float((recovered - raw).abs().max()),
                    }
                )
    save(a.out / "guard-probe.json", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
