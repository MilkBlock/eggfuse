"""Read-only post-decision audit of seeded replay versus canonical CCP publication."""

import numpy as np
import torch
from binding_online import trial
from binding_model import read_packet, tensor
from first_parent import records
from joint_partner import model, batch
from joint_partner_eval import generate
from joint_partner_worlds import options, folder


@torch.no_grad()
def audit(a):
    rows = []
    for i in (300001, 300009):
        for n in (32, 256, 1024):
            for f in (0, 1):
                d = folder(a, ("held", i, n, "two", f, True))
                canonical = []
                for seed in a.seeds:
                    net = model(a, seed, "wide")
                    if not canonical:

                        def collect(client, z, p, rng):
                            paid = generate(net)(client, z, p, rng)
                            canonical.append(z)
                            return paid

                        trial(a, d, "context", net, seed, generate=collect)
                    frozen = read_packet(d / "binding.pkl")
                    values = [
                        b["hash"][j, :3]
                        for b, j in zip(frozen["banks"], frozen["gold"][0])
                    ]
                    for arm in ("independent", "wide"):
                        probe = model(a, seed, arm)
                        for mode, z in (
                            ("named-replay", frozen),
                            ("canonical", canonical[0]),
                        ):
                            # Match the verified value tuple only AFTER live sampling.
                            y = [
                                np.flatnonzero((b["hash"][:, :3] == v).all(1)).item()
                                for b, v in zip(z["banks"], values)
                            ]
                            for copy in (True, False):
                                query = (
                                    z
                                    if copy
                                    else dict(
                                        z, banks=[dict(b, last=-1) for b in z["banks"]]
                                    )
                                )
                                inp, link = batch([query])
                                future, t = probe.messages(inp, link)
                                ps, _ = probe.decode(
                                    inp, future, t, tensor(np.array([[y]])), None
                                )
                                rows.append(
                                    dict(
                                        n=n,
                                        i=i,
                                        f=f,
                                        seed=seed,
                                        arm=arm,
                                        context=mode,
                                        copy=int(copy),
                                        last_root=int(z["banks"][0]["last"] == y[0]),
                                        root_index=y[0],
                                        prior=float(
                                            probe.local.root_prior(inp)[0, y[0]].exp()
                                        ),
                                        message=float(future[0][0, y[0]]),
                                        root=float(ps[0][0, 0, y[0]].exp()),
                                        second=float(ps[1][0, 0, y[1]].exp()),
                                    )
                                )
    records(a.out / "context.csv", rows)


if __name__ == "__main__":
    a = options().parse_args()
    torch.set_num_threads(1)
    audit(a)
