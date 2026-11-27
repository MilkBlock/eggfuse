"""Boundary-value and field intervention probes; only verified native fixtures form labels."""

import numpy as np
import torch
from binding_model import parser, Decoder, collate, tensor, read_packet, bit_lanes
from binding_worlds import build
from binding_packets import packet
from completion_context import write
from actor import row_features
from pathlib import Path


@torch.no_grad()
def check(a):
    b = (1 << 53) + 1
    text = f"""(relation Edge (i64 i64 i64))
(relation Result (i64 i64))
(ruleset warm) (ruleset probe)
(rule ((Edge x y z) (Edge y w v)) ((Result x v)) :ruleset probe)
(Edge -9223372036854775808 {b} 91)
(Edge {b} -27 9223372036854775807)
(Edge {b - 1} 67 33)
(Edge 73 82 79)
(run-schedule (run warm) (run probe))
"""
    job = ("precision", 60000, 4, "eq10", 0, False, False)
    build(a, job, override=text)
    d = a.out / "worlds/precision/0004-eq10-60000-0"
    packet(a, d)
    z = read_packet(d / "binding.pkl")
    (goal,) = z["gold"]
    assert z["banks"][0]["raw"][goal[0], 1] == z["banks"][1]["raw"][goal[1], 0] == b
    numbers = [0, 1, 2**53, 2**53 + 1, 2**63 - 1, 2**63, 2**64 - 1]
    enc = bit_lanes(numbers, True)
    assert len(np.unique(enc, axis=0)) == len(numbers)
    # The old single-row encoder reads a 32-bit window in column zero.
    collide = torch.equal(*row_features([(3,), (3 ^ (1 << 47),)], 32, "cpu").unbind())
    result = []
    for seed in a.seeds:
        for arm in ("C", "D"):
            net = Decoder(a, arm).to("mps").eval()
            net.load_state_dict(
                torch.load(
                    a.out / "weights" / str(seed) / f"{arm}.pt", weights_only=True
                )
            )
            for raw in (False, True):
                p = (
                    net(collate([z], raw), tensor(np.array([[goal]])))[0][1]
                    .exp()[0, 0]
                    .cpu()
                    .numpy()
                )
                wrong = next(
                    i for i, x in enumerate(z["banks"][1]["raw"]) if x[0] == b - 1
                )
                result.append(
                    dict(
                        seed=seed,
                        arm=arm,
                        raw_i64=raw,
                        correct=float(p[goal[1]]),
                        off_by_one=float(p[wrong]),
                    )
                )
    write(
        a.out / "precision.json",
        dict(old_column0_collision=collide, bit_patterns=len(numbers), results=result),
    )


if __name__ == "__main__":
    p = parser()
    p.add_argument("--compiler", type=Path, required=True)
    torch.set_num_threads(1)
    check(p.parse_args())
