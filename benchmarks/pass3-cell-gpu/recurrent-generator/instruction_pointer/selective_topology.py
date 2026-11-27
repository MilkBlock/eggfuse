"""Intervene on the root's incoming messages while preserving both conditional decoders."""

import numpy as np
import torch
from binding_model import read_packet, tensor
from first_parent import records
from selective_kernel import net
from selective_trials import inputs
from selective_worlds import args, path


@torch.no_grad()
def run(a):
    rows = []
    for seed in a.seeds:
        m = net(a, seed, "mixed-sparse")
        for kind in ("chain", "fork", "parity"):
            for n in (32, 256, 1024, 4096):
                paths = (
                    list(
                        (a.previous_joint / "worlds/parity").glob(
                            f"{n:04}-*/binding.pkl"
                        )
                    )
                    if kind == "parity"
                    else [
                        path(a, ("square", n, kind, 390001, f)) / "binding.pkl"
                        for f in (0, 1)
                    ]
                )
                for p in paths:
                    z = read_packet(p)
                    data = inputs(z, False)
                    inp, edges = data
                    (gold,) = z["gold"]
                    y = tensor(np.array([[gold]]))
                    future = m.flow(*data)

                    def msg(child):
                        par, cols = edges[child - 1]
                        left = m.encode(inp[3][par][1], cols[:, :, 0])
                        right = m.encode(inp[3][child][1], cols[:, :, 1])
                        return m.evidence_from(
                            left, m.summarize(right, torch.ones_like(future[child]))
                        )

                    choices = {"full": future[0]}
                    if kind == "chain":
                        choices["without-tail-at-root"] = msg(1)
                    if kind == "fork":
                        choices.update(only_mid=msg(1), only_tail=msg(2))
                    for mode, v in choices.items():
                        ps, _ = m.draw(data, [v, *future[1:]], y, None)
                        pp = [float(lp[0, 0, j].exp()) for lp, j in zip(ps, gold)]
                        rows.append(
                            dict(
                                seed=seed,
                                kind=kind,
                                n=n,
                                state=p.parent.name,
                                mode=mode,
                                first=pp[0],
                                complete=np.prod(pp),
                            )
                        )
    records(a.out / "topology.csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
