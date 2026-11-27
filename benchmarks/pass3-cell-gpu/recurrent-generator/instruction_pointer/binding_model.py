"""Complete-token CE with a dense address control and optional field attention."""

from functools import lru_cache
from pathlib import Path
import pickle
import random
import time
import numpy as np
import torch
from torch import nn

from address_scores import mlp, tree, weight
from completion_fit import cohort
from completion_context import write
from discovery_states import cli
from query_fit import batch
from rule_read import load_actor

DEVICE = "mps"


def read_packet(path):
    with path.open("rb") as f:
        return pickle.load(f)


def bit_lanes(values, raw=False):
    x = np.asarray(values, dtype=np.uint64)
    if raw:
        # Bijection on 64-bit words. Signed values arrive as exact two's-complement.
        x = x ^ (x >> np.uint64(30))
        x = x * np.uint64(0xBF58476D1CE4E5B9)
        x = x ^ (x >> np.uint64(27))
        x = x * np.uint64(0x94D049BB133111EB)
        x = x ^ (x >> np.uint64(31))
    return ((x[..., None] >> np.arange(64, dtype=np.uint64)) & 1).astype(
        np.float32
    ) * 2 - 1


def tensor(x):
    return torch.from_numpy(np.asarray(x)).to(DEVICE)


def collate(states, raw=False):
    def stack(name):
        return tensor(np.stack([s[name] for s in states]))

    banks = []
    for j in range(len(states[0]["banks"])):
        b = [s["banks"][j] for s in states]
        banks.append(
            (
                tensor(np.stack([p["row"] for p in b])),
                tensor(
                    bit_lanes(np.stack([p["raw" if raw else "hash"] for p in b]), raw)
                ),
                tensor(np.array([p["last"] for p in b])),
            )
        )
    return stack("h"), stack("roles"), stack("wires"), banks


@lru_cache(maxsize=64)
def routes(n):
    left, right, paths, bits, mask, _ = tree(n)
    return [tensor(v) for v in (left, right, paths, bits, mask)]


class Decoder(nn.Module):
    def __init__(self, a, arm):
        super().__init__()
        self.arm = arm
        self.scorer = weight(a)
        self.gate = weight(a).requires_grad_(False)
        self.gru = load_actor(a.actor, True).next_read.requires_grad_(False)
        self.scorer.load_state_dict(torch.load(a.initial, weights_only=True))
        if arm in ("C", "D"):
            self.metric = nn.Parameter(torch.zeros(64, 64))
            self.wire_gain = nn.Parameter(torch.tensor(2.0))
        if arm == "D":
            self.alpha = nn.Parameter(torch.zeros(()))

    def addresses(self, q, key, last):
        b, s, _ = q.shape
        n = key.shape[1]
        if n == 1:
            return q.new_zeros(b, s, 1)
        is_tree = self.arm in ("A", "finite", "B")
        if is_tree:
            l, r, path, right, mask = routes(n)
            u = q[:, :, None, :].expand(b, s, n - 1, 32)
            v = mlp(
                self.scorer,
                u,
                key[:, None, l].expand_as(u),
                key[:, None, r].expand_as(u),
                1,
            )
            base = (
                nn.functional.logsigmoid(v[:, :, path] * (2 * right.float() - 1))
                .masked_fill(~mask, 0)
                .sum(-1)
                .exp()
            )
        else:
            u = q[:, :, None, :].expand(b, s, n, 32)
            v = key[:, None].expand_as(u)
            zero = torch.zeros_like(v)
            scores = (
                mlp(self.scorer, u, zero, v, 1) - mlp(self.scorer, u, v, zero, 1)
            ) / 2
            base = scores.softmax(-1)
        ids = torch.arange(b, device=q.device)
        anchor = key[ids, last.clamp_min(0)][:, None].expand_as(q)
        bypass = mlp(self.gate, q, anchor, torch.zeros_like(q), 2).sigmoid()
        copy = ((1 - bypass) * (last >= 0)[:, None])[:, :, None]
        return (
            (
                base * (1 - copy)
                + copy * (torch.arange(n, device=q.device) == last[:, None])[:, None]
            )
            .clamp_min(1e-30)
            .log()
        )

    def forward(self, inputs, teacher=None, draws=1, noise=None, remove_wiring=False):
        h, roles, wires, banks = inputs
        b = len(h)
        s = teacher.shape[1] if teacher is not None else draws
        h = h[:, None].expand(-1, s, -1)
        history = []
        probs = []
        picks = []
        ids = torch.arange(b, device=h.device)[:, None]
        for j, (keys, fields, last) in enumerate(banks):
            slot = roles[:, None, j, :]
            q = (h + slot).tanh()
            score = self.addresses(q, keys, last)
            if j and self.arm in ("C", "D"):
                # The only link information here is static Recipe column sharing.
                # Every candidate field in the role receives a neural score.
                w = wires[:, j, :j]
                if remove_wiring:
                    w = torch.zeros_like(w)
                attn = (self.wire_gain * w.flatten(1)).softmax(-1).view_as(w)
                past = torch.stack(history, 2)
                ctx = torch.einsum("bspfv,bpfg->bsgv", past, attn)
                projected = ctx @ self.metric
                if self.arm == "D":
                    projected = projected + self.alpha * ctx
                score = score + torch.einsum("bsgv,bngv->bsn", projected, fields) / 8
            lp = score.log_softmax(-1)
            if teacher is None:
                # Samples of the actual conditional distribution, one uniform per slot.
                u = noise[:, :, j, None]
                selected = (
                    (lp.exp().cumsum(-1) < u).sum(-1).clamp_max(keys.shape[1] - 1)
                )
            else:
                selected = teacher[:, :, j]
            probs.append(lp)
            picks.append(selected)
            history.append(fields[ids, selected])
            if j + 1 < len(banks):
                h = self.gru(
                    (keys[ids, selected] + slot).reshape(-1, 32), h.reshape(-1, 32)
                ).view(b, s, 32)
        return probs, torch.stack(picks, -1)


def make_batches(states, seed, width):
    rng = random.Random(seed)
    groups = {}
    for idx, z in enumerate(states):
        shape = (z["layout"], tuple(len(b["row"]) for b in z["banks"]))
        groups.setdefault(shape, []).append(idx)
    blocks = []
    for group in groups.values():
        rng.shuffle(group)
        blocks.extend(group[i : i + width] for i in range(0, len(group), width))
    rng.shuffle(blocks)
    return blocks


def train(a):
    from copy import copy

    old = copy(a)
    old.out = a.previous_corpus
    legacy = [cohort(old, n, False) for n in (4, 8, 16, 32, 64, 128, 256, 1024)]
    states = [
        read_packet(p) for p in sorted((a.out / "worlds/train").glob("*/binding.pkl"))
    ]
    if len(states) != a.count:
        raise ValueError(len(states))
    small = {}
    for z in states:
        k = (z["layout"], z["size"], bool(z["warm"]))
        bucket = small.setdefault(k, [])
        if len(bucket) < 4:
            bucket.append(z)
    for seed in a.seeds:
        blocks = make_batches(states, seed, 8)
        for arm in a.arms:
            dest = a.out / "weights" / str(seed)
            dest.mkdir(exist_ok=True, parents=True)
            torch.manual_seed(seed)
            rng = np.random.default_rng(seed)
            net = Decoder(a, arm).to(DEVICE)
            pars = [dict(params=net.scorer.parameters(), lr=0.00015)]
            if arm in ("C", "D"):
                pars.append(
                    dict(
                        params=[
                            p for name, p in net.named_parameters() if "." not in name
                        ],
                        lr=0.008,
                    )
                )
            opt = torch.optim.AdamW(pars, weight_decay=0)
            steps = []
            losses = []
            seen = 0
            start = time.perf_counter()
            for step, block in enumerate(blocks, 1):
                zs = [states[i] for i in block]
                if arm == "A":
                    st, offs = legacy[rng.integers(len(legacy))]
                    ix = rng.integers(len(offs) - 1, size=len(block))
                    ix = rng.integers(offs[ix], offs[ix + 1])
                    loss = -batch(net.scorer, st, ix, DEVICE)[0].logsumexp(1).mean()
                else:
                    if arm == "finite":
                        zs = [
                            (v := small[z["layout"], z["size"], bool(z["warm"])])[
                                rng.integers(len(v))
                            ]
                            for z in zs
                        ]
                    y = tensor(
                        np.array(
                            [[z["gold"][rng.integers(len(z["gold"]))]] for z in zs]
                        )
                    )
                    ps, _ = net(collate(zs), y)
                    loss = -sum(
                        p.gather(-1, y[:, :, j, None]).mean() for j, p in enumerate(ps)
                    )
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(net.parameters(), 5)
                opt.step()
                seen += len(block)
                losses.append(loss.detach())
                if step % 64 == 0 or step == len(blocks):
                    steps.append(
                        dict(
                            step=step,
                            exposures=seen,
                            ce=float(torch.stack(losses).mean()),
                            seconds=time.perf_counter() - start,
                        )
                    )
                    losses = []
            torch.save(net.cpu().state_dict(), dest / f"{arm}.pt")
            write(dest / f"{arm}.json", steps)
            print(seed, arm, steps[-1], flush=True)


def parser():
    p = cli()
    p.add_argument("--initial", type=Path, required=True)
    p.add_argument("--previous-corpus", type=Path)
    p.add_argument("--count", type=int, default=4096)
    p.add_argument("--seeds", type=int, nargs="+", default=[9633, 5003, 1777])
    p.add_argument("--arms", nargs="+", default=["A", "finite", "B", "flat", "C", "D"])
    return p


if __name__ == "__main__":
    torch.set_num_threads(1)
    train(parser().parse_args())
