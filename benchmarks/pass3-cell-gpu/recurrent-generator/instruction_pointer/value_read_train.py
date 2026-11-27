"""Counterbalanced complete-token CE. Cache frozen Memory and batch exact singleton entry reads."""

import os

import numpy as np
import torch

from cell_kv_world import World
from partner_index_worlds import args
from token_embedding_study import fixed_digest, save
from value_read_model import ValueRead, lane_products
from value_read_world import CUBES, SCHEMAS, key

SEEDS = (71, 113)
SINGLE = 420
STEPS = 1680


def mode():
    scale = os.environ.get("VALUE_READ_SCALE", "rich")
    if scale not in ("pilot", "small", "rich"):
        raise ValueError(scale)
    return scale


def output(a):
    path = a.out if mode() == "pilot" else a.out / mode()
    path.mkdir(parents=True, exist_ok=True)
    return path


def load(a):
    return torch.load(
        a.out / ("corpus-rich.pt" if mode() == "rich" else "corpus.pt"),
        weights_only=False,
    )


def training(a):
    data = load(a)
    pools = range(72001, 72033) if mode() == "rich" else range(71001, 71007)
    for seed in SEEDS:
        for variant in "ABC":
            net = ValueRead(a, variant).train()
            initial = fixed_digest(net)
            rng = np.random.default_rng(seed)
            opt = torch.optim.AdamW(
                (p for p in net.parameters() if p.requires_grad),
                lr=0.002,
                weight_decay=0,
            )
            cache = {}
            for schema in SCHEMAS:
                w = World(a.out / "worlds" / key(schema, 71001, CUBES[0]), net.actor)
                net.prepare(w)
                targets = []
                values = []
                external = []
                words = []
                others = []
                first = []
                with torch.no_grad():
                    for pool in pools:
                        for bits in CUBES:
                            rows = data[key(schema, pool, bits)]
                            s, ts = rows[0]
                            m = net.state(w, s)
                            assert len(m["refs"]) == len(m["owners"]) == 1
                            (t,) = [
                                t
                                for t, r in ts
                                if t >= w.primitives and r == (m["refs"][0],)
                            ]
                            targets.append(m["menu"].index(t))
                            words.append(s["ports"][0][4])
                            values.append(m["vals"][0])
                            external.append(net.actor.latent(m["ext"])[0])
                            first.append((s, (t, (m["refs"][0],))))
                            others.append(rows[1:])
                    codes = net.cache[1][s["menu"]]
                    lanes, role = lane_products(words)
                    V = torch.stack(values)
                    E = torch.stack(external)
                    prob = net.singleton(codes, V, E, lanes, role)
                    for i in (0, 7, 25):
                        s, token = first[i]
                        mem = net.state(w, s)
                        torch.testing.assert_close(
                            prob[i], mem["lp"], rtol=1e-5, atol=2e-5
                        )
                        torch.testing.assert_close(
                            -prob[i, targets[i]],
                            net.token_loss(w, mem, token),
                            rtol=1e-5,
                            atol=2e-5,
                        )
                    cache[schema] = (
                        w,
                        codes,
                        V,
                        E,
                        lanes,
                        role,
                        torch.tensor(targets),
                        others,
                    )
            losses = []
            for step in range(STEPS):
                # Balanced minibatches contain complete truth cubes, not a single
                # physical address. Each block visits all eligible Recipe identities.
                if step < SINGLE:
                    schema = SCHEMAS[0]
                else:
                    if (step - SINGLE) % len(SCHEMAS) == 0:
                        order = rng.permutation(len(SCHEMAS))
                    schema = SCHEMAS[order[(step - SINGLE) % len(SCHEMAS)]]
                w, codes, V, E, lanes, role, y, later = cache[schema]
                net.prepare(w)
                idx = torch.tensor(
                    (
                        rng.choice(len(pools), 3, replace=False)[:, None] * 8
                        + np.arange(8)
                    ).flatten()
                )
                logits = net.singleton(codes, V[idx], E[idx], lanes[idx], role)
                loss = -logits.gather(1, y[idx, None]).mean()
                # Include a legal Primitive alternative and real post-publication continuations.
                if mode() == "pilot":
                    loss = 24 * loss - logits[[0, -1], 0].sum()
                    exposure = 28
                else:
                    # All eight corners get the same Primitive alternative frequency.
                    loss = 24 * loss - logits[:8, 0].sum()
                    exposure = 34
                assert w.menu([w.root])[0] == w.root
                for ix in idx[:2]:
                    rows = later[int(ix)]
                    s, ts = rows[int(rng.integers(len(rows)))]
                    target = ts[int(rng.integers(len(ts)))]
                    loss += net.token_loss(w, net.state(w, s), target)
                loss = loss / exposure
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 3.0)
                opt.step()
                losses.append(float(loss.detach()))
                if step + 1 in (SINGLE, STEPS):
                    path = output(a) / f"{variant}-{seed}-{step + 1}.pt"
                    torch.save(net.state_dict(), path)
                    assert fixed_digest(net) == initial
                    save(
                        path.with_suffix(".json"),
                        {
                            "ce60": [
                                float(np.mean(losses[i : i + 60]))
                                for i in range(0, len(losses), 60)
                            ],
                            "updates": step + 1,
                            "frozen": initial,
                            "complete_targets": (step + 1) * exposure,
                            "trainable": sum(
                                p.numel() for p in net.parameters() if p.requires_grad
                            ),
                        },
                    )
                    print(path.name, losses[-1], flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    training(args())
