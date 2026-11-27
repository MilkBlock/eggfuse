"""Free named requests replayed from the prefix; teacher forcing is a separate diagnostic."""

from collections import defaultdict
import numpy as np
import torch

from binding_model import collate, Decoder, parser, read_packet, tensor
from completion_context import native, read, write
from discrete_draft import Cell
from discovery_score import packet


@torch.no_grad()
def evaluate(a):
    paths = sorted(
        p
        for split in (
            "test",
            "noise",
            "cross-guard",
            *[f"subset-{n}" for n in range(4)],
            *[f"density-{n}" for n in (4, 8, 16, 32, 64)],
        )
        for p in (a.out / "worlds" / split).glob("*/binding.pkl")
    )
    for seed in a.seeds:
        models = {}
        for arm in a.arms:
            net = Decoder(a, arm).to("mps").eval()
            net.load_state_dict(
                torch.load(
                    a.out / "weights" / str(seed) / f"{arm}.pt", weights_only=True
                )
            )
            models[arm] = net
        for idx, path in enumerate(paths):
            d = path.parent
            dest = d / f"eval-{seed}.json"
            if dest.exists():
                continue
            z = read_packet(path)
            inp = collate([z])
            k = len(z["banks"])
            result = []
            noise = (
                np.random.default_rng(seed + z["instance"])
                .random((1, a.draws, k))
                .astype(np.float32)
            )
            for arm, net in models.items():
                parts = []
                width = min(16, a.draws) if z["size"] >= 128 else a.draws
                for l in range(0, a.draws, width):
                    u = tensor(noise[:, l : l + width])
                    _, pick = net(inp, draws=u.shape[1], noise=u)
                    parts.extend(map(tuple, pick[0].cpu().tolist()))
                # Finalize neural choices before consulting the verified next-token set.
                tape = read(d / "prefix.json")
                base = max([q["token"] for q in tape["requests"]] + [0]) + 1
                cells = [
                    Cell(z["rule"], tuple(z["addrs"][j][p] for j, p in enumerate(refs)))
                    for refs in parts
                ]
                probe = d / f"free-tape-{seed}.json"
                write(
                    probe,
                    dict(
                        tape,
                        requests=tape["requests"]
                        + [packet(c, 2, base + i) for i, c in enumerate(cells)],
                    ),
                )
                rep = native(a, d, "replay", probe, 2, "--ept-origins")
                probe.unlink()
                gained = dict(rep["ept"]["origins"])
                gold = set(map(tuple, z["gold"]))
                group = dict(
                    zip(
                        map(tuple, z["gold"]),
                        z.get("groups", range(len(gold))),
                        strict=True,
                    )
                )
                hits = [p in gold for p in parts]
                novel = sum(gained.get(base + i, 0) for i in range(len(parts)))
                if novel != len({group[p] for p in set(parts) & gold}):
                    raise ValueError(
                        (d, arm, novel, len({group[p] for p in set(parts) & gold}))
                    )
                y = tensor(np.array([z["gold"]]))
                ps, _ = net(inp, y)
                joint = (
                    sum(p.gather(-1, y[:, :, j, None]) for j, p in enumerate(ps))
                    .exp()
                    .sum()
                    .item()
                )

                def diagnostics(probs):
                    stages = []
                    for j, p in enumerate(probs):
                        prefixes = defaultdict(dict)
                        for l, refs in enumerate(z["gold"]):
                            targets = prefixes[tuple(refs[:j])]
                            targets[refs[j]] = l
                        masses = []
                        wins = []
                        for group in prefixes.values():
                            at = next(iter(group.values()))
                            dist = p[0, at].exp().cpu().numpy()
                            masses.append(float(dist[list(group)].sum()))
                            wins.append(int(int(dist.argmax()) in group))
                        stages.append((float(np.mean(masses)), float(np.mean(wins))))
                    return stages

                cond = diagnostics(ps)
                # Named physical permutations aligned by the native operand values
                # only after decoding. These fingerprints never enter a query.
                bank = z["banks"][1]
                ref = z["gold"][0][0]
                canonical = list(map(tuple, z["banks"][0]["raw"][:, :3].tolist()))
                ref = min((x[0] for x in z["gold"]), key=lambda ix: canonical[ix])
                at = next(l for l, g in enumerate(z["gold"]) if g[0] == ref)
                order = sorted(
                    range(len(bank["raw"])), key=lambda i: tuple(bank["raw"][i, :3])
                )
                probs = ps[1][0, at].exp().cpu().numpy()[order]
                row = dict(
                    arm=arm,
                    seed=seed,
                    layout=z["layout"],
                    size=z["size"],
                    domain=len(bank["raw"]),
                    owners=z["owners"],
                    instance=z["instance"],
                    order=z["order"],
                    split=z["split"],
                    mass=joint,
                    conditional=cond,
                    draws=len(parts),
                    hits=sum(hits),
                    effective=novel,
                    gold=len(set(group.values())),
                    signed=len(cells),
                    receipts=rep["counts"],
                    recalls=[
                        len({group[p] for p in set(parts[:b]) & gold})
                        / len(set(group.values()))
                        for b in (1, 4, 16, a.draws)
                    ],
                    second_distribution=probs.tolist(),
                )
                if (
                    arm in ("C", "D")
                    and z["size"] == 4
                    and z["layout"].startswith("eq")
                ):
                    row["unwired"] = diagnostics(net(inp, y, remove_wiring=True)[0])[1]
                    row["raw_i64"] = diagnostics(net(collate([z], True), y)[0])[1]
                result.append(row)
            write(dest, result)
            if idx % 50 == 0:
                print(seed, idx, flush=True)


if __name__ == "__main__":
    p = parser()
    p.add_argument("--draws", type=int, default=32)
    torch.set_num_threads(1)
    evaluate(p.parse_args())
