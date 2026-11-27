"""Frozen mixed sparse features for weighted direct partner draws. No semantic lookup."""

from dataclasses import dataclass
import torch
from selective_kernel import build_index, view

EXPLORE = 1 / 256
ATTEMPTS = 8


def take(sparse, rows):
    ids, v = sparse
    ix = rows[:, None, :, None].expand(-1, ids.size(1), -1, 2)
    return ids.gather(2, ix), v.gather(2, ix)


def ranges(q, index):
    ids, v = q
    keys, scan, _ = index
    terms = ids.flatten(2).contiguous()
    low = torch.searchsorted(keys, terms)
    high = torch.searchsorted(keys, terms, right=True)
    start = scan.gather(-1, low).view_as(v)
    end = scan.gather(-1, high).view_as(v)
    return start, end


def head_affinities(q, b):
    # Per requested ROW PAIR only. Compare learned feature coordinates; intersections
    # of the two interpolated supports yield the dot product in a head.
    qi, qv = q
    bi, bv = b
    return (
        (qi.unsqueeze(-1) == bi.unsqueeze(-2)) * qv.unsqueeze(-1) * bv.unsqueeze(-2)
    ).sum((-2, -1))


def affinity(q, b):
    return head_affinities(q, b).mean(1)


def categorical(mass, u):
    cdf = mass.cumsum(-1)
    total = cdf[..., -1:]
    # Bound a rounded endpoint strictly below the total positive mass.
    target = torch.minimum(u * total, torch.nextafter(total, torch.zeros_like(total)))
    return torch.searchsorted(
        cdf.contiguous(), target.contiguous(), right=True
    ).clamp_max(mass.size(-1) - 1)


def proposals(q, index, noise):
    """noise is B x slots x attempts x 2; generate all attempts without device sync."""
    start, end = ranges(q, index)

    def flatten(x):
        return x.transpose(1, 2).flatten(2)

    mass = flatten(q[1] * (end - start))
    ch = categorical(mass, noise[..., 0])
    lo = flatten(start).gather(-1, ch)
    hi = flatten(end).gather(-1, ch)
    target = torch.minimum(lo + noise[..., 1] * (hi - lo), torch.nextafter(hi, lo))
    _, scan, refs = index
    B, H, L = refs.shape
    # Packed search over all heads avoids materializing a posting list per slot.
    ptr = torch.searchsorted(
        scan, target.flatten(1)[:, None].expand(-1, H, -1).contiguous(), right=True
    )
    head = (ch // 2).reshape(B, 1, -1)
    off = (ptr.gather(1, head).squeeze(1) - 1).clamp(0, L - 1)
    row = refs.flatten(1).gather(1, head[:, 0] * L + off).long().view_as(ch)
    return row, mass.sum(-1)


@dataclass
class Edge:
    query: tuple
    partner: tuple
    index: tuple


def prepare(m, data):
    inp, layout = data
    future = [b[0].new_zeros(b[0].shape[:2]) for b in inp[3]]
    edges = [None] * len(layout)
    for j in reversed(range(1, len(future))):
        i, cols = layout[j - 1]
        q = m.encode(inp[3][i][1], cols[:, :, 0])
        v = m.encode(inp[3][j][1], cols[:, :, 1])
        weights = future[j].softmax(1) * future[j].size(1)
        idx = build_index(v, weights, named=True)
        future[i] += m.evidence_from(q, idx[:2])
        edges[j - 1] = Edge(q, v, idx)
    return future, edges


def conditional(edge, root, u, arm, strength=None):
    # u carries independent uniforms for channel, within-channel, rejection and
    # exploration. If all attempts fail the last independent linear draw is used.
    q = take(edge.query, root)
    if arm not in ("linear", "refined", "shared-score"):
        raise ValueError(arm)
    attempts = ATTEMPTS if arm != "linear" else 0
    count = attempts if arm == "shared-score" else attempts + 1
    draws, mass = proposals(q, edge.index, u[:, :, :count, :2])
    picked = draws[:, :, -1]
    if attempts:
        cand = draws[:, :, :attempts]
        q_rep = tuple(t.repeat_interleave(attempts, dim=2) for t in q)
        heads = head_affinities(q_rep, take(edge.partner, cand.flatten(1)))
        kernel = heads.mean(1).view_as(cand)
        if arm == "shared-score":
            # Importance resampling with the SAME frozen nonlinear head readout.
            # Downstream weights occur in both target and proposal, and cancel.
            logits = (
                strength.exp() * ((heads + 1e-5).log() - heads.log1p()).sum(1)
            ).view_as(cand)
            weights = (logits - kernel.clamp_min(1e-30).log()).softmax(-1)
            chosen = categorical(weights, u[:, :, 0, 2:3])
            picked = cand.gather(-1, chosen).squeeze(-1)
        else:
            accept = u[:, :, :attempts, 2] < kernel.pow(3)
            first = accept.int().argmax(-1, keepdim=True)
            picked = torch.where(
                accept.any(-1), cand.gather(-1, first).squeeze(-1), picked
            )
    n = edge.partner[0].size(2)
    uniform = (u[:, :, 0, 4] * n).long().clamp_max(n - 1)
    choice = torch.where((mass <= 0) | (u[:, :, 0, 3] < EXPLORE), uniform, picked)
    return choice, draws


def draw(m, data, state, u, arm):
    inp, layout = data
    future, edges = state
    root = (m.local.root_prior(inp) + future[0]).softmax(-1)
    refs = [categorical(root, u[:, :, 0, 0, 0])]
    touches = []
    for j, (parent, _) in enumerate(layout, 1):
        if arm == "legacy":
            score = (
                m.local.relation(view(inp, parent, j), refs[parent])
                + future[j][:, None]
            )
            ix = categorical(score.softmax(-1), u[:, :, j, 0, :1]).squeeze(-1)
        else:
            ix, used = conditional(
                edges[j - 1], refs[parent], u[:, :, j], arm, m.local.strength
            )
            touches.append(used)
        refs.append(ix)
    return torch.stack(refs, -1), touches


def noise(rng, slots, arity):
    from binding_model import tensor

    return tensor(rng.random((1, slots, arity, ATTEMPTS + 1, 5), dtype="float32"))


def dense_kernel(edge, root):
    """Offline single-parent diagnostic only. No complete parent Cartesian product."""
    q = take(edge.query, root)
    return affinity(q, edge.partner)
