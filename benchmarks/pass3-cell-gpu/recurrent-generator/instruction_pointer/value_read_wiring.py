"""Trace static wiring and conditional scores with every input field held constant."""

import torch

from cell_kv_runtime import native
from cell_kv_study import digest
from cell_kv_world import World
from partner_index_worlds import args
from token_embedding_study import save
from value_read_model import ValueRead
from value_read_train import STEPS, output
from value_read_world import CUBES, key


@torch.no_grad()
def audit(a):
    net = ValueRead(a, "C").eval()
    net.load_state_dict(torch.load(output(a) / f"C-71-{STEPS}.pt", weights_only=True))
    rows = []
    for g in (0, 1):
        for o in (0, 1):
            for bits in CUBES:
                pair = []
                for wire in (0, 1):
                    w = World(
                        a.out / "worlds" / key((wire, g, o), 71001, bits), net.actor
                    )
                    s, ts = native(a, w, teacher="higher")[0]
                    (t,) = [t for t, r in ts if t >= w.primitives]
                    net.prepare(w)
                    m = net.state(w, s)
                    body = w.layouts[-2]
                    rid = body[1][0]
                    nodes, codes, _ = net.cache
                    pair.append(
                        (
                            s,
                            w.prog["recipe"]["sha256"],
                            digest(w),
                            nodes[w.cat.roots["generated", rid]],
                            codes[-2:],
                            m["keys"],
                            m["lp"][
                                [
                                    m["menu"].index(t)
                                    for t in (w.primitives, w.primitives + 1)
                                ]
                            ],
                            t - w.primitives,
                        )
                    )
                l, r = pair
                assert l[0] == r[0]
                gap = l[6][0] - l[6][1] - (r[6][0] - r[6][1])
                rows.append(
                    {
                        "guard": g,
                        "op": o,
                        "bits": list(bits),
                        "different_choice": l[-1] != r[-1],
                        "recipe_diff": l[1] != r[1],
                        "signature_diff": [
                            x != y for x, y in zip(l[2], r[2], strict=True)
                        ],
                        "guard_node_l2": float((l[3] - r[3]).norm()),
                        "higher_l2": (l[4] - r[4]).norm(dim=1).tolist(),
                        "key_l2": float((l[5] - r[5]).norm()),
                        "margin_shift": float(gap),
                    }
                )
    save(output(a) / "wiring-audit.json", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    audit(args())
