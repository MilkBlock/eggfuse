"""Frozen EggCC conditional transfer and physical midpoint-tree field ablation."""

from collections import Counter, defaultdict
from pathlib import Path
import json
import numpy as np
import torch
from address_scores import tree, mlp
from binding_model import Decoder, parser, tensor, collate, read_packet
from binding_packets import public_view
from completion_context import read, write
from query_environment import conditioned
from recursive_train import folder


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
    rows = []
    counts = Counter()
    for case in ("fact", "loopfact", "sum-divisors"):
        d = folder(a.data, case)
        prog = read(d / "program.json")
        for source in ("teacher", "rollout"):
            base = a.archive / source / case
            m = conditioned(a, d, base / "scheduler.jsonl")
            runs = sorted(s["run"] for s in read(base / "states.json"))[:8]
            contexts = (
                read(a.archive / "dirty" / case / "contexts.json")
                if source == "rollout"
                else {}
            )
            try:
                for line in (base / "frames.jsonl").open():
                    frame = json.loads(line)
                    r = frame["run"]
                    if r > max(runs):
                        break
                    m.update(frame)
                    if r not in runs:
                        continue
                    if contexts:
                        last, event, state, ctx = contexts[str(r)]
                        m.last = tuple(last) if last else None
                        m.event, m.state = torch.tensor(event), torch.tensor(state)
                        torch.testing.assert_close(
                            m.context(), torch.tensor(ctx), rtol=0, atol=0
                        )
                    by_rule = defaultdict(list)
                    for q, g in read(base / str(r) / "gold.json"):
                        if g > 0 and len(q["parents"]) >= 2:
                            by_rule[q["rule"]].append(q)
                    for rid, qs in by_rule.items():
                        stat = prog["recipe"]["rules"][rid]["interface"]["rows"][:2]
                        counts["positive_prefix_rows"] += len(qs)
                        if (rid, False) not in m.ids or any(
                            len(row["columns"]) > 4 for row in stat
                        ):
                            counts["unsupported_rows"] += len(qs)
                            continue
                        z = public_view(m, prog, key=(rid, False), limit=2)
                        if not all(z["addrs"]):
                            continue
                        idx = [
                            {addr: j for j, addr in enumerate(bank)}
                            for bank in z["addrs"]
                        ]
                        prefixes = defaultdict(set)
                        for q in qs:
                            pair = []
                            for j, p in enumerate(q["parents"][:2]):
                                loc = (
                                    p["address"]["token"],
                                    p["address"]["op"],
                                    p["version"],
                                )
                                if loc in idx[j]:
                                    pair.append(idx[j][loc])
                            if len(pair) == 2:
                                prefixes[pair[0]].add(pair[1])
                            else:
                                counts["address_absent"] += 1
                        inp = collate([z])
                        for first, seconds in prefixes.items():
                            y = tensor(np.array([[[first, min(seconds)]]]))
                            for (seed, arm), net in models.items():
                                p = net(inp, y)[0][1].exp()[0, 0].cpu().numpy()
                                rows.append(
                                    dict(
                                        case=case,
                                        source=source,
                                        run=r,
                                        rule=rid,
                                        first=first,
                                        seed=seed,
                                        arm=arm,
                                        second_mass=float(p[list(seconds)].sum()),
                                        top1=int(p.argmax() in seconds),
                                        uniform=len(seconds) / len(p),
                                        domain=len(p),
                                        wires=int(z["wires"].sum()),
                                    )
                                )
            finally:
                m.close_observer()
    write(a.out / "egg-prefix.json", dict(rows=rows, counts=counts))
    # Only nodes on the path to the named target. Each split reads two physical
    # representative leaves. No subtree scan, pooled similarity or search hints.
    sparse = []
    for path in sorted((a.out / "worlds/test").glob("*-eq10-*/binding.pkl")):
        z = read_packet(path)
        inp = collate([z])
        h, roles, w, banks = inp
        for (seed, arm), net in models.items():
            if arm not in ("C", "D"):
                continue
            metrics = []
            for first, second in z["gold"]:
                h1 = net.gru(banks[0][0][:, first] + roles[:, 0], h)
                q = (h1 + roles[:, 1]).tanh()
                k, fields, _ = banks[1]
                n = k.shape[1]
                k = k[0]
                fields = fields[0]
                att = (net.wire_gain * w[0, 1, 0].flatten()).softmax(0).reshape(4, 4)
                ctx = att.T @ banks[0][1][0, first]
                proj = ctx @ net.metric + (net.alpha * ctx if arm == "D" else 0)

                def components(key, cols):
                    u = q.expand_as(key)
                    b = torch.zeros_like(key)
                    return (
                        mlp(net.scorer, u, b, key, 1) - mlp(net.scorer, u, key, b, 1)
                    ) / 2, (cols * proj).sum((1, 2)) / 8

                l, r, paths, right, mask, _ = tree(n)
                nodes = paths[second, mask[second]]
                a1, b1 = components(k[l[nodes]], fields[l[nodes]])
                a2, b2 = components(k[r[nodes]], fields[r[nodes]])
                sign = tensor(
                    np.where(right[second, mask[second]], 1.0, -1.0).astype(np.float32)
                )
                ps = ((a2 + b2 - a1 - b1) * sign).sigmoid().prod().item()
                flat, rel = components(k, fields)
                dense = (flat.log_softmax(0) + rel).softmax(0)[second].item()
                metrics.append((ps, dense, 2 * len(nodes)))
            sparse.append(
                dict(
                    size=z["size"],
                    instance=z["instance"],
                    order=z["order"],
                    seed=seed,
                    arm=arm,
                    metrics=np.mean(metrics, 0).tolist(),
                )
            )
    write(a.out / "sparse.json", sparse)


if __name__ == "__main__":
    p = parser()
    p.add_argument("--archive", type=Path, required=True)
    torch.set_num_threads(1)
    run(p.parse_args())
