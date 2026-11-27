"""Offline full-domain sampling for selected roots, and three-parent native transfer."""

from tempfile import TemporaryDirectory
from pathlib import Path
import numpy as np
import torch
from binding_model import read_packet, tensor
from first_parent_trials import free_replay
from first_parent import records
from selective_trials import inputs
from binding_online import trial
from completion_context import native
from partner_index_worlds import args, folder, frozen
from partner_index_trials import policy
from partner_index import categorical, prepare, take, EXPLORE, draw, noise


@torch.no_grad()
def run(a):
    dense = []
    transfer = []
    with TemporaryDirectory() as tmp:
        for n in (1024, 8192, 32768):
            for i in (511000, 511001):
                for f in (0, 1):
                    seed = a.seeds[(i - 511000) % len(a.seeds)]
                    m = frozen(a, seed)
                    d = folder(a, ("hard", n, i, f))
                    z = read_packet(d / "binding.pkl")
                    data = inputs(z, False)
                    future, edges = prepare(m, data)
                    e = edges[0]
                    prior = (m.local.root_prior(data[0]) + future[0])[0]
                    truth = z["gold"][0][0]
                    other = prior.clone()
                    other[truth] = -torch.inf
                    competitor = int(other.argmax())
                    rng = np.random.default_rng([seed, i, f, 90])
                    roots = categorical(
                        prior.softmax(-1)[None],
                        tensor(rng.random((1, 32), dtype="float32")),
                    )[0]
                    ri, rv = e.partner

                    def score(indices):
                        qi, qv = take(e.query, indices[None])
                        hi = qi[:, :, :, None, :, None] == ri[:, :, None, :, None, :]
                        val = (
                            hi * qv[:, :, :, None, :, None] * rv[:, :, None, :, None, :]
                        ).sum((-2, -1))
                        return val[0]

                    wrong = score(torch.tensor([competitor], device=prior.device))[:, 0]
                    valid = score(torch.tensor([truth], device=prior.device))[:, 0]
                    ck = float(wrong.mean(0).max())
                    tk = float(valid.mean(0).max())
                    top_head_count = int((wrong > 0).any(1).sum())
                    overlap = int((wrong > 0).all(0).sum())
                    targets = {}
                    for k in range(0, 32, 4):
                        h = score(roots[k : k + 4])
                        kernel = h.mean(0)
                        den = kernel.sum(-1, keepdim=True)
                        old_soft = (
                            m.local.strength.exp()
                            * ((h + 1e-5).log() - h.log1p()).sum(0)
                        ).softmax(-1)
                        linear = (
                            torch.where(den > 0, kernel / den.clamp_min(1e-30), 1 / n)
                            * (1 - EXPLORE)
                            + EXPLORE / n
                        )
                        u = tensor(rng.random((4, 1), dtype="float32"))
                        for arm, p in [
                            ("dense-nonlinear", old_soft),
                            ("dense-linear", linear),
                        ]:
                            second = categorical(p, u).flatten()
                            targets.setdefault(arm, []).extend(
                                zip(roots[k : k + 4].tolist(), second.tolist())
                            )
                    for arm, choices in targets.items():
                        ops, _ = free_replay(a, d, z, choices, Path(tmp))
                        hits = choices.count(tuple(z["gold"][0]))
                        assert ops == int(hits > 0)
                        dense.append(
                            dict(
                                n=n,
                                i=i,
                                f=f,
                                seed=seed,
                                arm=arm,
                                paid=32,
                                hits=hits,
                                ops=ops,
                                root_rank=1 + int((prior > prior[truth]).sum()),
                                wrong_max_k=ck,
                                true_max_k=tk,
                                winning_wrong_heads=top_head_count,
                                wrong_partners_in_all_heads=overlap,
                            )
                        )
    records(a.out / "dense.csv", dense)
    for kind in ("chain", "fork"):
        for seed in a.seeds:
            m = frozen(a, seed)
            for f in (0, 1):
                d = a.selective / "worlds/square" / f"1024-{kind}-390001-{f}"
                ref = native(a, d, "reference", "-")["state_sha"]
                for arm in ("legacy", "linear", "refined"):
                    row = trial(
                        a,
                        d,
                        arm,
                        m,
                        seed,
                        address_seed=72931 + f + seed,
                        generate=policy(m, arm, seed, 390001, f, 32),
                    )
                    assert bool(row["ops"]) == (row["graph"] == ref)
                    transfer.append(
                        dict(
                            kind=kind,
                            seed=seed,
                            f=f,
                            arm=arm,
                            ops=row["ops"],
                            paid=row["paid"],
                            seconds=row["seconds"],
                        )
                    )
    records(a.out / "trees.csv", transfer)
    prefixes = []
    with TemporaryDirectory() as tmp:
        for flip in (0, 1):
            d = folder(a, ("multi", 8192, 511000, flip))
            z = read_packet(d / "binding.pkl")
            data = inputs(z, False)
            goals = {tuple(x) for x in z["gold"]}
            for seed in a.seeds:
                m = frozen(a, seed)
                state = prepare(m, data)
                for arm in ("linear", "refined"):
                    rng = np.random.default_rng([seed, flip, 298])
                    history = []
                    for page in range(4):
                        ix, _ = draw(m, data, state, noise(rng, 32, 2), arm)
                        history.extend(map(tuple, ix[0].tolist()))
                    for b in (1, 4, 8, 16, 32, 64, 128):
                        distinct = goals.intersection(history[:b])
                        ops, _ = free_replay(a, d, z, history[:b], Path(tmp))
                        assert ops == len(distinct)
                        prefixes.append(
                            dict(
                                seed=seed,
                                flip=flip,
                                arm=arm,
                                paid=b,
                                ops=ops,
                                novel_partner_ordinals=" ".join(
                                    str(x[1]) for x in sorted(distinct)
                                ),
                            )
                        )
    records(a.out / "prefixes.csv", prefixes)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
