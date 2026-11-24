"""Shared binary decisions over the Bake codes of eligible subtrees."""

from collections import defaultdict
import math
import torch
from torch import nn
from torch.nn import functional as F
from generation_higher import Layouts
from higher_replacement import split
from generation_higher import BAKE
from template_routing import records
from recursive_train import folder, read
from ripsat_replay import unpack
from protocol_experiment import dump


def tree(codes, ids):
    """A negative child encodes a template, a nonnegative child another decision."""
    desc = []
    children = []
    paths = {}

    def build(group, prefix):
        if len(group) == 1:
            paths[group[0]] = prefix
            return -1 - group[0]
        bank = codes[group]
        axis = int(bank.var(0, unbiased=False).argmax())
        group = sorted(group, key=lambda i: (float(codes[i, axis]), i))
        n = len(group) // 2
        left, right = group[:n], group[n:]
        node = len(desc)
        desc.append(torch.cat((codes[left].mean(0), codes[right].mean(0))))
        children.append(None)
        children[node] = (
            build(left, prefix + [(node, 0)]),
            build(right, prefix + [(node, 1)]),
        )
        return node

    root = build(ids, [])
    return (
        root,
        torch.stack(desc) if desc else codes.new_empty(0, 2 * codes.shape[1]),
        torch.tensor(children, dtype=torch.long).reshape(-1, 2),
        paths,
    )


class TreeNet(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.gate = nn.Sequential(nn.Linear(28, 16), nn.Tanh(), nn.Linear(16, 1))
        self.query = nn.Sequential(nn.Linear(28, 24), nn.Tanh())
        self.key = nn.Sequential(nn.Linear(width, 24), nn.Tanh(), nn.Linear(24, 24))

    def keys(self, pairs):
        left, right = pairs.chunk(2, dim=1)
        return self.key(right) - self.key(left)


def fit(root, out, donor_dir):
    donor = read(donor_dir / "program.json")
    units = unpack(read(BAKE / "catalog.json"))
    groups = list(map(split, units))
    gate_x = []
    gate_y = []
    xs = []
    edges = []
    ys = []
    for case in (donor_dir, "loopfact"):
        d = folder(root, case) if isinstance(case, str) else case
        cat = Layouts(read(d / "program.json"))
        cached = {}
        glob = {k: i for i, k in enumerate(cat.original)}
        for x, menu, positive in records(root, case, donor, True):
            if menu not in cached:
                ids = [
                    glob[k]
                    for k in menu
                    if groups[k] == "fit"
                    and all(i == g for i, (_, g, _) in enumerate(units[k]))
                ]
                cached[menu] = tree(cat.codes, ids) if ids else None
            if cached[menu] is None:
                continue
            _, vec, _, paths = cached[menu]
            actions = defaultdict(set)
            legal = [glob[k] for k in positive if glob[k] in paths]
            gate_x.append(x)
            gate_y.append(bool(legal))
            for uid in legal:
                for node, b in paths[uid]:
                    actions[node].add(b)
            for node, bs in actions.items():
                if len(bs) == 1:
                    xs.append(x)
                    edges.append(vec[node])
                    ys.append(next(iter(bs)))
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    torch.manual_seed(9461)
    net = TreeNet(cat.codes.shape[1]).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=0.003)
    gx = torch.stack(gate_x).to(dev)
    gy = torch.tensor(gate_y, device=dev).float()
    x = torch.stack(xs).to(dev)
    v = torch.stack(edges).to(dev)
    y = torch.tensor(ys, device=dev).float()
    for _ in range(600):
        a = torch.randint(len(gx), (160,), device=dev)
        b = torch.randint(len(x), (160,), device=dev)
        loss = F.binary_cross_entropy_with_logits(net.gate(gx[a]).flatten(), gy[a])
        loss += F.binary_cross_entropy_with_logits(
            (net.keys(v[b]) * net.query(x[b])).sum(1), y[b]
        )
        opt.zero_grad()
        loss.backward()
        opt.step()
    torch.save(net.cpu().state_dict(), out / "tree.pt")
    dump(
        out / "tree-fit.json",
        dict(
            seed=9461,
            device=dev,
            steps=600,
            gates=len(gx),
            positive_gates=int(gy.sum()),
            branch_labels=len(y),
        ),
    )


class TreeRouter:
    def __init__(self, cat, out):
        self.codes = cat.codes
        self.net = TreeNet(cat.codes.shape[1]).eval()
        self.net.load_state_dict(torch.load(out / "tree.pt", weights_only=True))

    def prepare(self, menu):
        root, keys, children, _ = tree(self.codes, menu)
        return root, self.net.keys(keys).detach(), children, len(menu)

    def select(self, x, compiled, counts):
        root, keys, children, n = compiled
        use = torch.where(self.net.gate(x).flatten() > 0)[0]
        result = torch.full((len(x),), -1, dtype=torch.long)
        counts["use_logits"] += len(x)
        counts["route_inputs"] += len(x)
        if root < 0:
            result[use] = -1 - root
            return result
        coords = self.net.query(x[use])
        nodes = torch.full((len(use),), root, dtype=torch.long)
        rows = torch.arange(len(use))
        for _ in range(math.ceil(math.log2(n))):
            if not len(rows):
                break
            b = (coords[rows] * keys[nodes]).sum(1) >= 0
            counts["tree_decisions"] += len(nodes)
            nodes = children[nodes, b.long()]
            done = nodes < 0
            result[use[rows[done]]] = -1 - nodes[done]
            nodes = nodes[~done]
            rows = rows[~done]
        if len(nodes):
            raise AssertionError("unresolved Bake address")
        return result
