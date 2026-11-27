"""Replace one native first-parent field and trace its effect on the next address odds."""

from copy import deepcopy
import random
from pathlib import Path
import numpy as np
import torch
from binding_model import parser, Decoder, collate, tensor, read_packet
from binding_worlds import build
from binding_packets import packet
from completion_context import write


@torch.no_grad()
def run(a):
    models = {}
    for seed in a.seeds:
        for arm in a.arms:
            net = Decoder(a, arm).to("mps").eval()
            net.load_state_dict(
                torch.load(
                    a.out / "weights" / str(seed) / f"{arm}.pt", weights_only=True
                )
            )
            models[seed, arm] = net
    results = []
    for i in range(12):
        index = 61000 + i
        nums = random.Random(index).sample(range(10**11, 10**12), 11)
        x, v, w, c, b, e, f, g, h, j, k = nums
        states = []
        for mode in ("base", "shared", "irrelevant"):
            rows = [
                (x, w if mode == "shared" else v, k if mode == "irrelevant" else c),
                (v, b, e),
                (w, f, g),
                (h, j, k),
            ]
            src = "(relation Edge (i64 i64 i64))\n(relation Out (i64 i64))\n(ruleset warm)\n(ruleset probe)\n(rule ((Edge x y z) (Edge y b c)) ((Out x c)) :ruleset probe)\n"
            src += (
                "\n".join(f"(Edge {aa} {bb} {cc})" for aa, bb, cc in rows)
                + "\n(run-schedule (run warm) (run probe))\n"
            )
            split = "query-" + mode
            job = (split, index, 4, "eq10", 0, False, False)
            build(a, job, override=src)
            d = a.out / "worlds" / split / f"0004-eq10-{index:05}-0"
            packet(a, d)
            states.append(read_packet(d / "binding.pkl"))
        z, u, irr = states
        ((anchor, target),) = z["gold"]
        ((other, new),) = u["gold"]
        assert (
            anchor == other
            and target != new
            and z["gold"] == irr["gold"]
            and all(s["addrs"] == z["addrs"] for s in states)
        )
        for (seed, arm), net in models.items():

            def probe(state):
                inp = collate([state])
                hh, roles, _, banks = inp
                q = (
                    net.gru(banks[0][0][:, anchor] + roles[:, 0], hh) + roles[:, 1]
                ).tanh()
                lp = net(inp, tensor(np.array([[[anchor, target]]])))[0][1][0, 0]
                return q, (lp[new] - lp[target]).item(), lp[new].exp().item()

            q0, odds, pnew = probe(z)
            for name, s in [("shared", u), ("irrelevant", irr)]:
                for route in ["row", "fields", "both"]:
                    state = deepcopy(z)
                    for part in (
                        ["row", "hash"]
                        if route == "both"
                        else ["row" if route == "row" else "hash"]
                    ):
                        state["banks"][0][part][anchor] = s["banks"][0][part][anchor]
                    q, od, p = probe(state)
                    results.append(
                        dict(
                            seed=seed,
                            arm=arm,
                            instance=i,
                            intervention=name,
                            path=route,
                            delta_log_odds=od - odds,
                            before=pnew,
                            after=p,
                            delta_query=float((q - q0).norm()),
                            delta_key=float(
                                np.linalg.norm(
                                    state["banks"][0]["row"][anchor]
                                    - z["banks"][0]["row"][anchor]
                                )
                            ),
                        )
                    )
    write(a.out / "query-probe.json", results)


if __name__ == "__main__":
    p = parser()
    p.add_argument("--compiler", type=Path, required=True)
    torch.set_num_threads(1)
    run(p.parse_args())
