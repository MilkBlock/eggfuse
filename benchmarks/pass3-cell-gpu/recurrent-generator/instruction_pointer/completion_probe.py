"""Separate fitting four physical snapshots from transfer of the same binding relation."""

from pathlib import Path
import numpy as np
import torch
from address_scores import weight
from completion_context import build, directory, frames, read, write

from discrete_cells import from_q
from discovery_states import cli
from next_cell_train import combine, read as packet
from query_fit import batch


def diagnose(a):
    gate = weight(a).to("mps").eval()
    net = weight(a).to("mps")
    net.load_state_dict(torch.load(a.initial, weights_only=True))
    opt = torch.optim.AdamW(net.parameters(), lr=0.00015, weight_decay=0)
    groups = {}
    for name, ip in [
        ("memorized", [(i, i % 2) for i in range(4)]),
        ("insertion_only", [(i, 1 - i % 2) for i in range(4)]),
        ("names_only", [(i, i % 2) for i in range(4)]),
        ("permuted", [(i, 1 - i % 2) for i in range(4)]),
        ("new_values", [(i, p) for i in [80, 81, *range(90, 106)] for p in (0, 1)]),
    ]:
        blocks = []
        diagnostics = []
        for i, p in ip:
            d = directory(a, 4, "pair", i, p)
            if name in {"insertion_only", "names_only"}:
                d = a.out / "small-interventions" / name / str(i)
                build(a, 4, "pair", i, p, gate, output=d, name_order=1 - p)
            elif not (d / "packet.pkl.gz").exists():
                build(a, 4, "pair", i, p, gate)
            blocks.append(packet(d / "packet.pkl.gz"))
            m = frames(a, d)
            try:
                import json

                for line in (d / "frames.jsonl").read_text().splitlines():
                    m.update(json.loads(line))
                (c,) = [
                    from_q(q)
                    for q in read(d / "verified.json")["requests"]
                    if q["run"] == 2
                ]
                keys = torch.stack([m.key(k) for k in m.rows[m.roles[c.rule][0]]])
                nodes = m.enc.nodes[m.enc.cat.inputs["generated", c.rule]]
                dist = torch.pdist(keys)
                diagnostics.append(
                    dict(
                        instance=i,
                        order=p,
                        physical_map=read(d / "world.json")["map_digest"],
                        key_min_separation=float(dist.min().detach()),
                        slot_distance=float((nodes[0] - nodes[1]).norm().detach()),
                        target=c.refs,
                    )
                )
            finally:
                m.close_observer()
        groups[name] = (combine(blocks), diagnostics)
    out = []
    train = groups["memorized"][0]
    for step in range(1025):
        if step in (0, 32, 128, 512, 1024):
            with torch.no_grad():
                for name, (s, diag) in groups.items():
                    mat, f = batch(net, s, np.arange(len(diag)), "mps")
                    out.append(
                        dict(
                            step=step,
                            split=name,
                            complete=mat.exp().flatten().tolist(),
                            factors=f.tolist(),
                            inputs=diag,
                        )
                    )
        if step == 1024:
            break
        loss = -batch(net, train, np.arange(4), "mps")[0].mean()
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 5)
        opt.step()
    torch.save(net.cpu().state_dict(), a.out / "small-fit.pt")
    write(a.out / "small-fit.json", out)


if __name__ == "__main__":
    p = cli()
    p.add_argument("--canonical-names", action="store_true")
    p.add_argument("--compiler", type=Path, required=True)
    p.add_argument("--initial", type=Path, required=True)
    torch.set_num_threads(1)
    diagnose(p.parse_args())
