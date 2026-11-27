"""Full-token CE for first-parent discovery. Dense joint energy is diagnostic only."""

import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import torch
from torch import nn

from binding_model import Decoder, collate, make_batches, parser, read_packet, tensor
from binding_packets import packet
from binding_worlds import build, source

SIZES = (4, 8, 16, 32)
ARMS = ("field", "joint", "pool")


def records(path, rows):
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def prepare(a):
    jobs = []
    for j, n in enumerate(SIZES):
        for i in range(96):
            layout = ("eq01", "eq12", "eq20", "joint")[i % 4]
            jobs.append(
                ("fit", 90000 + j * 96 + i, n, layout, i % 2, False, i % 9 == 0)
            )
    for i in range(48):
        jobs.append(("guard-fit", 100000 + i, 4, "guard", i % 2, False, False))

    def compile_world(job):
        if job[0] == "guard-fit":
            _, i, n, l, p, *_ = job
            build(a, job, override=source(i, n, l, p, cross_guard=True))
        else:
            build(a, job)

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(compile_world, jobs))
    for path in sorted((a.out / "worlds").glob("*/*/ok.json")):
        packet(a, path.parent)


def sample(lp, u):
    return (lp.exp().cumsum(-1) < u[..., None]).sum(-1).clamp_max(lp.shape[-1] - 1)


class FirstParent(nn.Module):
    def __init__(self, a, seed, arm):
        super().__init__()
        self.arm = arm
        self.base = Decoder(a, "C")
        self.base.load_state_dict(
            torch.load(
                a.previous_binding / "weights" / str(seed) / "C.pt", weights_only=True
            )
        )
        if arm == "pool":
            # Shared soft neural feature map. All 128 channels get scored for each
            # field in each of four heads. Neither addresses nor value pairs are keys.
            signs = (
                (torch.arange(128)[:, None] >> torch.arange(7)) % 2
            ).float() * 2 - 1
            gen = torch.Generator().manual_seed(109)
            indices = torch.randperm(64, generator=gen)[:28].reshape(4, 7)
            self.register_buffer("coordinates", indices)
            self.prototypes = nn.Parameter(signs.T.expand(4, -1, -1).clone() * 2)
            self.strength = nn.Parameter(torch.tensor(1.0))

    def root_prior(self, inputs):
        h, roles, _, banks = inputs
        return self.base.addresses(
            (h + roles[:, 0]).tanh()[:, None], banks[0][0], banks[0][2]
        )[:, 0]

    def role_attention(self, inputs):
        w = inputs[2][:, 1, 0]
        return (self.base.wire_gain * w.flatten(1)).softmax(-1).view_as(w)

    def relation(self, inputs, ids):
        _, roles, _, banks = inputs
        first, second = banks
        bi = torch.arange(len(ids), device=ids.device)[:, None]
        prev = first[1][bi, ids]
        ctx = torch.einsum("bsfv,bfg->bsgv", prev, self.role_attention(inputs))
        field = torch.einsum("bsgv,bngv->bsn", ctx @ self.base.metric, second[1]) / 8
        h = inputs[0][:, None].expand(-1, ids.shape[1], -1)
        h = self.base.gru(
            (first[0][bi, ids] + roles[:, None, 0]).reshape(-1, 32), h.reshape(-1, 32)
        ).view_as(h)
        return field + self.base.addresses(
            (h + roles[:, None, 1]).tanh(), second[0], second[2]
        )

    def pool_scores(self, inputs):
        left, right = [bank[1] for bank in inputs[3]]

        def encode(x):
            sub = x[..., self.coordinates]
            return torch.einsum("bnfhc,hck->bnfhk", sub, self.prototypes).softmax(-1)

        # Sum over right rows first. There is no tensor with both address axes.
        summary = encode(right).sum(1)
        evidence = torch.einsum("bnfhk,bghk->bnfgh", encode(left), summary)
        # Saturate repeated occupancy; require support across heads and wired fields.
        log_support = (evidence + 1e-5).log() - torch.log1p(evidence)
        return self.strength.exp() * torch.einsum(
            "bnfgh,bfg->bn", log_support, self.role_attention(inputs)
        )

    def forward(self, inputs, teacher=None, draws=1, noise=None):
        if self.arm == "field":
            return self.base(inputs, teacher, draws, noise)
        prior = self.root_prior(inputs)
        batch, n = prior.shape
        joint = None
        if self.arm == "joint":
            if max(n, inputs[3][1][0].shape[1]) > 32:
                raise ValueError("dense joint diagnostic limited to 32 per role")
            every = torch.arange(n, device=prior.device).expand(batch, -1)
            joint = self.relation(inputs, every) + prior[:, :, None]
            root = joint.logsumexp(-1).log_softmax(-1)
        else:
            root = (prior + self.pool_scores(inputs)).log_softmax(-1)
        count = teacher.shape[1] if teacher is not None else draws
        root = root[:, None].expand(-1, count, -1)
        first = (
            teacher[:, :, 0] if teacher is not None else sample(root, noise[:, :, 0])
        )
        logits = (
            self.relation(inputs, first)
            if joint is None
            else joint[torch.arange(batch, device=first.device)[:, None], first]
        )
        second = logits.log_softmax(-1)
        partner = (
            teacher[:, :, 1] if teacher is not None else sample(second, noise[:, :, 1])
        )
        return [root, second], torch.stack((first, partner), -1)


def load(a, seed, arm, device="mps"):
    net = FirstParent(a, seed, arm).to(device)
    net.load_state_dict(
        torch.load(a.out / "weights" / f"{seed}-{arm}.pt", weights_only=True)
    )
    return net.eval()


def train(a):
    all_states = [
        read_packet(p) for p in sorted((a.out / "worlds/fit").glob("*/binding.pkl"))
    ]
    assert len(all_states) == 384
    dest = a.out / "weights"
    dest.mkdir(exist_ok=True)
    curves = []
    for seed in a.seeds:
        for arm in ARMS:
            net = FirstParent(a, seed, arm).to("mps")
            opt = torch.optim.AdamW(
                [
                    {"params": net.base.scorer.parameters(), "lr": 0.0001},
                    {"params": [net.base.metric, net.base.wire_gain], "lr": 0.003},
                ]
                + (
                    [{"params": [net.prototypes, net.strength], "lr": 0.002}]
                    if arm == "pool"
                    else []
                ),
                weight_decay=0,
            )
            rng = np.random.default_rng(seed)
            seen = 0
            for stage, maximum in enumerate(SIZES):
                states = [s for s in all_states if s["size"] <= maximum]
                losses = []
                for epoch in range(3):
                    for ids in make_batches(states, seed + 100 * stage + epoch, 8):
                        zs = [states[i] for i in ids]
                        target = tensor(
                            np.array(
                                [[z["gold"][rng.integers(len(z["gold"]))]] for z in zs]
                            )
                        )
                        ps, _ = net(collate(zs), target)
                        loss = -sum(
                            p.gather(-1, target[:, :, j, None]).mean()
                            for j, p in enumerate(ps)
                        )
                        opt.zero_grad()
                        loss.backward()
                        nn.utils.clip_grad_norm_(net.parameters(), 5)
                        opt.step()
                        seen += len(zs)
                        losses.append(loss.detach())
                curves.append(
                    dict(
                        seed=seed,
                        arm=arm,
                        maximum=maximum,
                        exposures=seen,
                        ce=float(torch.stack(losses).mean()),
                    )
                )
            torch.save(net.cpu().state_dict(), dest / f"{seed}-{arm}.pt")
            print(seed, arm, curves[-1], flush=True)
    records(a.out / "training.csv", curves)


def options():
    p = parser()
    p.add_argument("task", choices=["prepare", "train", "eval", "live", "guard"])
    p.add_argument("--reuse-guard-weights", action="store_true")
    p.add_argument("--previous-binding", type=Path, required=True)
    p.add_argument("--compiler", type=Path, required=True)
    return p


if __name__ == "__main__":
    a = options().parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    if a.task == "prepare":
        prepare(a)
    elif a.task == "train":
        train(a)
    else:
        from first_parent_trials import run

        run(a)
