"""Row-local joint feature maps, sum over partner rows, then address named parents."""

import numpy as np
import torch
from torch import nn
from binding_model import collate, make_batches, read_packet, tensor
from first_parent import FirstParent, records, sample
from joint_partner_worlds import ARMS, options


def links(z):
    # Compilation over Recipe variables only, independent of Memory values.
    return [
        [
            (i, j)
            for i, s in enumerate(a)
            for j, t in enumerate(b)
            if s is not None and s == t
        ]
        for a, b in zip(z["slots"], z["slots"][1:])
    ]


def batch(zs):
    by_state = [links(z) for z in zs]
    return collate(zs), [
        tensor(np.array([q[j] for q in by_state], dtype=np.int64))
        for j in range(len(by_state[0]))
    ]


def edge_view(inp, j):
    h, r, w, b = inp
    return h, r[:, j : j + 2], w[:, j : j + 2, j : j + 2], b[j : j + 2]


def align(x, idx):
    return x.gather(2, idx[:, None, :, None].expand(-1, x.size(1), -1, x.size(3)))


def signs(bits):
    return (
        (((torch.arange(1 << bits)[:, None] >> torch.arange(bits)) % 2) * 2 - 1)
        .float()
        .T
    )


class Partner(nn.Module):
    def __init__(self, a, seed, arm):
        super().__init__()
        self.arm = arm
        self.local = FirstParent(a, seed, "pool")
        self.local.load_state_dict(
            torch.load(
                a.previous_first / "weights" / f"{seed}-pool.pt", weights_only=True
            )
        )
        self.bits = 10 if arm == "wide" else 7
        if arm in ("cell", "tensor", "wide"):
            rng = torch.Generator().manual_seed(109)
            self.register_buffer(
                "coords",
                torch.randperm(64, generator=rng)[: 4 * self.bits].reshape(
                    4, self.bits
                ),
            )
            if arm == "cell":
                self.mix = nn.Parameter(torch.randn(3, 4, 7, generator=rng))
                self.codes = nn.Parameter(2 * signs(7).expand(4, -1, -1).clone())
            else:
                self.factors = nn.ParameterDict(
                    {
                        str(k): nn.Parameter(2 * signs(k).expand(4, -1, -1).clone())
                        for k in (2, 3, 4, 5)
                    }
                )

    def phi(self, x):
        # Input axes: batch, row, aligned field, identity bit.
        d = x.shape[2]
        if self.arm == "cell":
            parts = [
                x[:, :, j, self.coords.roll(j * 2, 1)] * self.mix[j] for j in range(d)
            ]
            joined = (sum(parts) / d**0.5).tanh()
            return torch.einsum("bnhc,hck->bnhk", joined, self.codes).softmax(-1)
        chunks = max(2, d)
        sizes = [
            self.bits // chunks + int(j < self.bits % chunks) for j in range(chunks)
        ]
        pos = 0
        out = None
        for j, k in enumerate(sizes):
            u = x[:, :, j % d, self.coords[:, pos : pos + k]]
            soft = torch.einsum("bnhc,hck->bnhk", u, self.factors[str(k)]).softmax(-1)
            out = (
                soft
                if out is None
                else (out.unsqueeze(-1) * soft.unsqueeze(-2)).flatten(-2)
            )
            pos += k
        return out

    def encode_side(self, x, columns):
        if self.arm == "independent":
            return torch.einsum(
                "bnfhc,hck->bnfhk",
                x[..., self.local.coordinates],
                self.local.prototypes,
            ).softmax(-1)
        return self.phi(align(x, columns))

    def features(self, edge, layout):
        return tuple(
            self.encode_side(bank[1], layout[:, :, j]) for j, bank in enumerate(edge[3])
        )

    def evidence(self, L, summary):
        if self.arm == "independent":
            return torch.einsum("bnfhk,bghk->bnfgh", L, summary)
        return torch.einsum("bnhk,bhk->bnh", L, summary)

    def reduce_score(self, e, edge):
        logs = (e + 1e-5).log() - torch.log1p(e)
        if self.arm == "independent":
            return self.local.strength.exp() * torch.einsum(
                "bnfgh,bfg->bn", logs, self.local.role_attention(edge)
            )
        return self.local.strength.exp() * logs.sum(-1)

    def messages(self, inp, layout):
        banks = inp[3]
        future = [None] * len(banks)
        dense = [None] * len(layout)
        future[-1] = banks[-1][0].new_zeros(banks[-1][0].shape[:2])
        for j in reversed(range(len(layout))):
            e = edge_view(inp, j)
            right = future[j + 1]
            n = e[3][0][0].size(1)
            if self.arm == "dense":
                if max(n, right.size(1)) > 32:
                    raise ValueError("offline dense edge diagnostic capped at 32")
                ids = torch.arange(n, device=right.device).expand(len(right), -1)
                dense[j] = self.local.relation(e, ids)
                future[j] = (dense[j] + right[:, None, :]).logsumexp(-1)
            else:
                L, R = self.features(e, layout[j])
                w = right.softmax(1) * right.size(1)
                summary = (R * w.view(*w.shape, *([1] * (R.ndim - 2)))).sum(1)
                future[j] = self.reduce_score(self.evidence(L, summary), e)
        return future, dense

    def decode(self, inp, future, dense, teacher, noise):
        B = len(inp[0])
        count = teacher.size(1) if teacher is not None else noise.size(1)
        lp = (
            (self.local.root_prior(inp) + future[0])
            .log_softmax(-1)[:, None]
            .expand(-1, count, -1)
        )
        ps = []
        refs = []
        for j in range(len(future)):
            if j:
                prev = refs[-1]
                edge = (
                    self.local.relation(edge_view(inp, j - 1), prev)
                    if dense[j - 1] is None
                    else dense[j - 1][
                        torch.arange(B, device=prev.device)[:, None], prev
                    ]
                )
                lp = (edge + future[j][:, None, :]).log_softmax(-1)
            ps.append(lp)
            refs.append(
                teacher[:, :, j] if teacher is not None else sample(lp, noise[:, :, j])
            )
        return ps, torch.stack(refs, -1)

    def forward(self, data, teacher=None, noise=None):
        inp, layout = data
        return self.decode(inp, *self.messages(inp, layout), teacher, noise)


def model(a, seed, arm, device="mps"):
    m = Partner(a, seed, arm)
    m.load_state_dict(
        torch.load(a.out / "weights" / f"{seed}-{arm}.pt", weights_only=True)
    )
    return m.to(device).eval()


def train(a):
    states = [
        read_packet(p) for p in sorted((a.out / "worlds/fit").glob("*/binding.pkl"))
    ]
    assert len(states) == 192
    (a.out / "weights").mkdir(exist_ok=True)
    rows = []
    for seed in a.seeds:
        for arm in ARMS:
            net = Partner(a, seed, arm).to("mps")
            opt = torch.optim.AdamW(
                [
                    {"params": net.local.base.scorer.parameters(), "lr": 0.0001},
                    {
                        "params": [
                            net.local.base.metric,
                            net.local.base.wire_gain,
                            net.local.strength,
                            net.local.prototypes,
                        ]
                        + [
                            p
                            for k, p in net.named_parameters()
                            if not k.startswith("local.")
                        ],
                        "lr": 0.003,
                    },
                ],
                weight_decay=0,
            )
            seen = 0
            for stage, n in enumerate((4, 8, 16, 32)):
                selected = [z for z in states if z["size"] <= n]
                losses = []
                for epoch in range(3):
                    for ids in make_batches(selected, seed + 100 * stage + epoch, 8):
                        zs = [selected[i] for i in ids]
                        y = tensor(np.array([z["gold"] for z in zs]))
                        ps, _ = net(batch(zs), teacher=y)
                        loss = -sum(
                            lp.gather(-1, y[:, :, j, None]).mean()
                            for j, lp in enumerate(ps)
                        )
                        opt.zero_grad()
                        loss.backward()
                        nn.utils.clip_grad_norm_(net.parameters(), 5)
                        opt.step()
                        losses.append(loss.detach())
                        seen += len(ids)
                rows.append(
                    dict(
                        seed=seed,
                        arm=arm,
                        max_size=n,
                        seen=seen,
                        ce=float(torch.stack(losses).mean()),
                    )
                )
            torch.save(net.cpu().state_dict(), a.out / "weights" / f"{seed}-{arm}.pt")
            records(a.out / "fit.csv", rows)
            print(rows[-1], flush=True)


if __name__ == "__main__":
    a = options().parse_args()
    torch.set_num_threads(1)
    if a.task == "train":
        train(a)
    else:
        from joint_partner_eval import run

        run(a)
