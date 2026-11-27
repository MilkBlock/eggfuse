"""Public-domain observations and sampled neural relation mass for template keys."""

import numpy as np
import torch

from address_scores import mlp
from binding_model import bit_lanes, tensor
from head_joint_index import PostingIndex
from partner_index import categorical


def plans(m, program):
    if not hasattr(m, "probe_layouts"):
        m.probe_layouts = []
        for rule in program["recipe"]["rules"]:
            slots = [
                [c.get("slot") for c in row["columns"]]
                for row in rule["interface"]["rows"]
            ]
            edges = (
                (
                    i,
                    j,
                    [
                        (p, q)
                        for p, s in enumerate(slots[i])
                        for q, t in enumerate(slots[j])
                        if s is not None and s == t
                    ],
                )
                for j in range(1, len(slots))
                for i in range(j)
            )
            m.probe_layouts.append(next((x for x in edges if x[2]), None))
    return m.probe_layouts


def features(model, m, program, run, arm="ce-support"):
    ids = [r for r, h in m.ids if not h]
    keys = tensor(torch.stack([m.graph((r, False)) for r in ids]).numpy())
    if arm == "ce-base":
        return (
            tensor(m.context().numpy()),
            keys,
            keys.new_zeros((len(ids), 4)),
            keys.new_zeros(len(ids)),
        )
    desc = plans(m, program)
    samples = {}
    sizes = np.zeros((len(ids), 4), np.float32)
    groups = {}
    probe = 8
    for ix, r in enumerate(ids):
        for j, tab in enumerate(m.roles[r]):
            if tab not in samples:
                bank = [m.pub.live[v][0] for v in m.rows[tab] if v in m.pub.live]
                n = len(bank)
                # Physical offsets only; new Run changes the probe. No restriction
                # on the final parent's domain, even if all probes miss.
                selected = (
                    np.random.default_rng([run, tab, 714]).choice(
                        n, min(probe, n), replace=False
                    )
                    if n and arm == "ce-support"
                    else []
                )
                samples[tab] = (n, [bank[k]["hashes"] for k in selected])
            if j < 4:
                sizes[ix, j] = np.log1p(samples[tab][0]) / 8
        edge = desc[r]
        if edge and arm == "ce-support":
            i, j, w = edge
            groups.setdefault(len(w), []).append((ix, m.roles[r][i], m.roles[r][j], w))
    support = keys.new_zeros(len(ids))
    for width, items in groups.items():
        sides = []
        masks = []
        for side in (0, 1):
            buf = np.zeros((len(items), probe, width), np.uint64)
            mask = np.zeros((len(items), probe), np.float32)
            for b, entry in enumerate(items):
                rows = samples[entry[side + 1]][1]
                if rows:
                    buf[b, : len(rows)] = np.asarray(rows, np.uint64)[
                        :, [p[side] for p in entry[3]]
                    ]
                    mask[b, : len(rows)] = 1
            sides.append(
                model.mapping(tensor(bit_lanes(buf)), model.variant, fixed_order=True)
            )
            masks.append(tensor(mask))
        idx = PostingIndex.build(sides[1], masks[1])
        mass = idx.lookup(sides[0])[2].sum(-1) * masks[0]
        support[tensor(np.array([x[0] for x in items]))] = mass.sum(-1).log1p()
    return tensor(m.context().numpy()), keys, tensor(sizes), support


def logits(net, features, arm):
    q, keys, sizes, support = features
    k = keys.clone()
    if arm in ("ce-count", "ce-support"):
        k[:, 12:16] += sizes
    if arm == "ce-support":
        k[:, 16] += support
    zero = torch.zeros_like(k)
    ctx = q.expand_as(k)
    return (mlp(net.gate, ctx, zero, k, 0) - mlp(net.gate, ctx, k, zero, 0)) / 2


def chooser(model, arm):
    def choose(net, m, program, noise):
        ids = [r for r, h in m.ids if not h]
        f = features(model, m, program, m.current_probe_run, arm)
        p = logits(net, f, arm).softmax(-1)
        ix = categorical(p[None], tensor(noise[:, 0].copy())[None])[0].tolist()
        return [ids[k] for k in ix]

    return choose
