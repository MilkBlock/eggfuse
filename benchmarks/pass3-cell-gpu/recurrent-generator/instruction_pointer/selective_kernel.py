"""Joint and fieldwise neural feature pooling. No parent-pair table in the online path."""

import math
import numpy as np
import torch
from torch import nn
from binding_model import collate, make_batches, read_packet, tensor
from first_parent import records, sample
from joint_partner import Partner, align
from selective_worlds import args

ARMS = ("wide", "positive", "field-sparse", "joint-sparse", "mixed-sparse")


def role_tree(slots):
    """Read one earlier producer role per child from static Recipe slots."""
    edges = []
    for j, child in enumerate(slots[1:], 1):
        choices = []
        for i, parent in enumerate(slots[:j]):
            shared = [
                (a, b)
                for a, s in enumerate(parent)
                for b, t in enumerate(child)
                if s is not None and s == t
            ]
            if shared:
                choices.append((i, shared))
        if len(choices) != 1:
            raise ValueError(
                "requires exactly one earlier connected role per child"
            )
        edges.append(choices[0])
    return edges


def pack(states):
    trees = [role_tree(z["slots"]) for z in states]
    parents = [p for p, _ in trees[0]]
    assert all([p for p, _ in t] == parents for t in trees)
    return collate(states), [
        (p, tensor(np.array([t[j][1] for t in trees], np.int64)))
        for j, p in enumerate(parents)
    ]


def view(inp, i, j):
    h, r, w, b = inp
    return h, r[:, [i, j]], w[:, [i, j]][:, :, [i, j]], (b[i], b[j])


class SparseMap(nn.Module):
    """Four scalar projections of public identity bits, each with two soft occupied bins."""

    def __init__(self):
        super().__init__()
        rng = torch.Generator().manual_seed(719)
        self.register_buffer(
            "coords",
            torch.stack([torch.randperm(64, generator=rng)[:22] for _ in range(4)]),
        )
        self.resolution = 262144
        self.logits = nn.Parameter(
            (-math.log(2) * torch.arange(22, dtype=torch.float32)).repeat(4, 1)
        )

    def forward(self, fields, variant, *, fixed_order=False):
        # B x N x fields x H x bits. Each head compares lossy learned feature coordinates.
        if variant == "mixed-sparse":
            # Each projected bit is an interaction across ALL aligned fields; a
            # one-field distractor no longer inherits half the address digits.
            selected = torch.stack(
                [
                    fields[:, :, j, self.coords.roll(7 * j, dims=1)]
                    for j in range(fields.size(2))
                ],
                dim=2,
            ).prod(dim=2, keepdim=True)
        else:
            selected = fields[..., self.coords]
        if variant == "joint-sparse":
            selected = torch.stack(
                [
                    selected[:, :, b % fields.size(2), :, b]
                    for b in range(self.coords.size(1))
                ],
                -1,
            ).unsqueeze(2)
        terms = (selected + 1) * 0.5 * self.logits.softmax(-1)
        if fixed_order:
            # MPS reduction order can vary with row-batch size. A fixed binary
            # tree makes publication-segment and full-bank encodings agree.
            parts = list(terms.unbind(-1))
            while len(parts) > 1:
                parts = [a + b for a, b in zip(parts[::2], parts[1::2])] + (
                    parts[-1:] if len(parts) % 2 else []
                )
            total = parts[0]
        else:
            total = terms.sum(-1)
        t = total * self.resolution
        t = t.flatten(2).transpose(1, 2)
        lo = t.floor()
        frac = t - lo
        return torch.stack((lo, lo + 1), -1).int(), torch.stack((1 - frac, frac), -1)


def build_index(sparse, weights, *, named=False):
    ids, values = sparse
    ids = ids.flatten(2)
    order = ids.argsort(-1)
    weights = (values * weights[:, None, :, None]).flatten(2)
    sorted_weights = weights.gather(-1, order)
    summary = ids.gather(-1, order).contiguous(), nn.functional.pad(
        sorted_weights.cumsum(-1), (1, 0)
    )
    if named:
        # Two entries per row; offsets resolve through this publication's immutable
        # role bank of (owner, op, version), even when equal feature bins collide.
        return (*summary, (order // 2).int())
    return summary


def read_index(sparse, index):
    ids, values = sparse
    ordered, scan = index
    q = ids.flatten(2).contiguous()
    a = torch.searchsorted(ordered, q).long()
    b = torch.searchsorted(ordered, q, right=True).long()
    count = (scan.gather(-1, b) - scan.gather(-1, a)).view_as(values)
    return (count * values).sum(-1).transpose(1, 2)


class Selective(Partner):
    def __init__(self, a, seed, arm):
        super().__init__(a, seed, "wide")
        self.load_state_dict(
            torch.load(
                a.previous_joint / "weights" / f"{seed}-wide.pt", weights_only=True
            )
        )
        self.variant = arm
        if arm.endswith("sparse"):
            self.mapping = SparseMap()

    def encode(self, x, cols):
        f = align(x, cols)
        if self.variant.endswith("sparse"):
            return self.mapping(f, self.variant)
        z = self.phi(f)
        # Positive separable kernel. Powers inside each feature map precede pooling.
        if self.variant == "positive":
            z = z.square()
            return z / z.sum(-1, keepdim=True).clamp_min(1e-12)
        return z

    def summarize(self, features, w):
        if self.variant.endswith("sparse"):
            return build_index(features, w)
        return (features * w[:, :, None, None]).sum(1)

    def evidence_from(self, l, summary):
        if self.variant.endswith("sparse"):
            e = read_index(l, summary)
        else:
            e = torch.einsum("bnhk,bhk->bnh", l, summary)
        log_e = torch.log(e.clamp_min(0) + 1e-5) - torch.log1p(e.clamp_min(0))
        return self.local.strength.exp() * 4 * log_e.mean(-1)

    def flow(self, inp, edges):
        fut = [b[0].new_zeros(b[0].shape[:2]) for b in inp[3]]
        for j in reversed(range(1, len(fut))):
            i, layout = edges[j - 1]
            w = fut[j].softmax(1) * fut[j].size(1)
            r = self.encode(inp[3][j][1], layout[:, :, 1])
            summary = self.summarize(r, w)
            l = self.encode(inp[3][i][1], layout[:, :, 0])
            fut[i] = fut[i] + self.evidence_from(l, summary)
        return fut

    def draw(self, data, future, gold, noise):
        inp, edges = data
        n = gold.size(1) if gold is not None else noise.size(1)
        root = self.local.root_prior(inp) + future[0]
        probs = []
        ids = []
        for j in range(len(future)):
            if not j:
                lp = root.log_softmax(-1)[:, None].expand(-1, n, -1)
            else:
                i, _ = edges[j - 1]
                lp = (
                    self.local.relation(view(inp, i, j), ids[i]) + future[j][:, None]
                ).log_softmax(-1)
            ids.append(
                gold[:, :, j] if gold is not None else sample(lp, noise[:, :, j])
            )
            probs.append(lp)
        return probs, torch.stack(ids, -1)

    def forward(self, data, teacher=None, noise=None):
        return self.draw(data, self.flow(*data), teacher, noise)


def net(a, seed, arm):
    m = Selective(a, seed, arm)
    if arm != "wide":
        m.load_state_dict(
            torch.load(a.out / "weights" / f"{seed}-{arm}.pt", weights_only=True)
        )
    return m.to("mps").eval()


def train(a):
    states = [
        read_packet(p)
        for p in sorted((a.previous_joint / "worlds/fit").glob("*/binding.pkl"))
    ]
    assert len(states) == 192
    (a.out / "weights").mkdir(exist_ok=True)
    rows = []
    for seed in a.seeds:
        for arm in ARMS[1:]:
            m = Selective(a, seed, arm).to("mps")
            params = [m.local.strength]
            params += (
                list(m.mapping.parameters())
                if arm.endswith("sparse")
                else list(m.factors.parameters())
            )
            opt = torch.optim.Adam(params, lr=0.001)
            seen = 0
            for stage, n in enumerate((4, 8, 16, 32)):
                chosen = [z for z in states if z["size"] <= n]
                losses = []
                for e in range(3):
                    for ix in make_batches(chosen, seed + 100 * stage + e, 8):
                        zs = [chosen[i] for i in ix]
                        y = tensor(np.array([z["gold"] for z in zs]))
                        p, _ = m(pack(zs), teacher=y)
                        loss = -sum(
                            lp.gather(-1, y[:, :, j, None]).mean()
                            for j, lp in enumerate(p)
                        )
                        m.zero_grad(set_to_none=True)
                        loss.backward()
                        nn.utils.clip_grad_norm_(params, 5)
                        opt.step()
                        losses.append(loss.detach())
                        seen += len(zs)
                rows.append(
                    dict(
                        seed=seed,
                        arm=arm,
                        n=n,
                        exposures=seen,
                        ce=torch.stack(losses).mean().item(),
                    )
                )
            torch.save(m.cpu().state_dict(), a.out / "weights" / f"{seed}-{arm}.pt")
            records(a.out / "fit.csv", rows)
            print(rows[-1], flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    train(args())
