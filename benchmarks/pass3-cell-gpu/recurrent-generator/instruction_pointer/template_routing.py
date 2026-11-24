"""Train direct and factorized addresses on the frozen Bake library."""

import argparse, json, math
from collections import defaultdict
from pathlib import Path
import torch
from torch import nn
from torch.nn import functional as F
from generation_higher import BAKE, Layouts, contexts
from higher_replacement import split
from recursive_agent import Reader
from recursive_train import read, folder
from ripsat_layout import capture
from ripsat_replay import unpack
from protocol_experiment import dump


def addresses():
    """Balanced binary partitions of static template encodings, local to each root."""
    units = unpack(read(BAKE / "catalog.json"))
    v = torch.load(BAKE / "codes.pt", weights_only=True)["codes"]
    by = defaultdict(list)
    for i, u in enumerate(units):
        by[u[0][0]].append(i)
    codes = {}

    def walk(ids, bits):
        if len(ids) == 1:
            codes[ids[0]] = bits
            return
        axis = int(v[ids].var(0, unbiased=False).argmax())
        ids = sorted(ids, key=lambda i: (float(v[i, axis]), i))
        mid = len(ids) // 2
        walk(ids[:mid], bits + (0,))
        walk(ids[mid:], bits + (1,))

    for ids in by.values():
        walk(ids, ())
    return codes, v


class RouteNet(nn.Module):
    def __init__(self, n, depth):
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(28, 32), nn.Tanh())
        self.direct = nn.Linear(32, n + 1)
        self.use = nn.Linear(32, 1)
        self.bits = nn.Linear(32, depth)


def records(root, case, donor, training):
    d = folder(root, case) if isinstance(case, str) else case
    prog = read(d / "program.json")
    cat = Layouts(prog)
    rd = Reader(prog, root, rename_seed=8819)
    units = unpack(read(BAKE / "catalog.json"))
    refs, _, occ, _ = capture(d, donor, 10, grow_consumers=True)
    by = defaultdict(list)
    for i, q in enumerate(refs):
        by[q["run"]].append((i, q))
    for f in map(json.loads, (d / "memory.jsonl").open()):
        rd.advance(f)
        for i, q in by[f["run"]]:
            menu = cat.by[q["rule"]]
            if not menu:
                continue
            good = {
                cat.original[cat.index[u]]
                for u, arr in occ.get(i, {}).items()
                if u in cat.index and any(ready and first for _, ready, first, _ in arr)
            }
            # An exclusively held-out positive is unknown in training.
            if training:
                fit = {k for k in good if split(units[k]) == "fit"}
                if good and not fit:
                    continue
                good = fit
            x = contexts(
                rd,
                q["rule"],
                [
                    (rd.store.alias(p["address"]["token"]), p["address"]["op"])
                    for p in q["parents"]
                ],
            )
            yield x, tuple(cat.original[k] for k in menu), good


def fit(root, out, donor_dir):
    donor = read(donor_dir / "program.json")
    data = [r for d in (donor_dir, "loopfact") for r in records(root, d, donor, True)]
    codes, _ = addresses()
    n = len(codes)
    depth = max(map(len, codes.values()))
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    torch.manual_seed(59197)
    model = RouteNet(n, depth).to(dev)
    # Marginalize the direct classifier over every observed valid choice.
    xs = []
    ys = []
    menus = []
    target_bits = []
    bit_mask = []
    units = unpack(read(BAKE / "catalog.json"))
    for x, menu, good in data:
        xs.append(x)
        ys.append([i in good or (i == n and not good) for i in range(n + 1)])
        train_ids = {i for i in menu if split(units[i]) == "fit"} | {n}
        menus.append([i in train_ids for i in range(n + 1)])
        # Canonical shortest address is one valid target when several layouts work.
        bits = min((codes[k] for k in good), key=lambda b: (len(b), b), default=())
        target_bits.append(bits + (0,) * (depth - len(bits)))
        bit_mask.append([i < len(bits) for i in range(depth)])
    x = torch.stack(xs).to(dev)
    y = torch.tensor(ys, device=dev)
    m = torch.tensor(menus, device=dev)
    t = torch.tensor(target_bits, device=dev).float()
    bm = torch.tensor(bit_mask, device=dev)
    opt = torch.optim.AdamW(model.parameters(), lr=0.003)
    for _ in range(600):
        i = torch.randint(len(x), (160,), device=dev)
        h = model.encoder(x[i])
        logits = model.direct(h)
        loss = (
            logits.masked_fill(~m[i], -1e4).logsumexp(1)
            - logits.masked_fill(~y[i], -1e4).logsumexp(1)
        ).mean()
        loss += F.binary_cross_entropy_with_logits(
            model.use(h).flatten(), (~y[i, -1]).float()
        )
        loss += (
            F.binary_cross_entropy_with_logits(model.bits(h), t[i], reduction="none")
            * bm[i]
        ).sum() / bm[i].sum().clamp_min(1)
        opt.zero_grad()
        loss.backward()
        opt.step()
    torch.save(model.cpu().state_dict(), out / "route.pt")
    dump(
        out / "route-fit.json",
        dict(
            device=dev,
            steps=600,
            examples=len(data),
            positive=sum(bool(g) for _, _, g in data),
            depth=depth,
            library=n,
        ),
    )


class Router:
    def __init__(self, cat, out, mode, limit=None):
        codes, _ = addresses()
        self.depth = max(map(len, codes.values()))
        self.n = len(codes)
        self.net = RouteNet(self.n, self.depth).eval()
        self.net.load_state_dict(torch.load(out / "route.pt", weights_only=True))
        self.mode = mode
        self.cache = {}
        self.codes = codes
        self.cat = cat
        self.limit = limit
        self.powers = 2 ** torch.arange(self.depth)
        # Direct array addressing. Different prefix lengths map to contiguous
        # sets of full-width codes. Lookup is per root with no directory scan.

    def prepare(self, menu):
        key = tuple(menu)
        if key not in self.cache:
            ids = [
                i
                for i in menu
                if self.limit is None or self.cat.original[i] < self.limit
            ]
            active = set()

            def compile_tree(group, depth):
                if len(group) == 1:
                    return group[0]
                left = [
                    i for i in group if self.codes[self.cat.original[i]][depth] == 0
                ]
                right = [
                    i for i in group if self.codes[self.cat.original[i]][depth] == 1
                ]
                if not left or not right:
                    return compile_tree(left or right, depth + 1)
                active.add(depth)
                return (
                    depth,
                    compile_tree(left, depth + 1),
                    compile_tree(right, depth + 1),
                )

            tree = compile_tree(ids, 0) if ids else -1
            levels = sorted(active)

            def leaf(mask, node):
                while isinstance(node, tuple):
                    depth, left, right = node
                    node = right if mask & (1 << levels.index(depth)) else left
                return node

            lut = torch.tensor([leaf(mask, tree) for mask in range(1 << len(levels))])
            bw = self.net.bits.weight[levels].detach()
            bb = self.net.bits.bias[levels].detach()
            indices = torch.tensor([self.cat.original[i] for i in ids] + [self.n])
            self.cache[key] = (
                lut,
                torch.tensor(ids + [-1]),
                self.net.direct.weight[indices].detach(),
                self.net.direct.bias[indices].detach(),
                bw,
                bb,
            )
        return self.cache[key]

    def select(self, x, compiled, counts):
        table, choices, w, b, bw, bb = compiled
        h = self.net.encoder(x)
        counts["route_inputs"] += len(x)
        if self.mode == "direct":
            counts["route_logits"] += len(x) * len(choices)
            return choices[F.linear(h, w, b).argmax(1)]
        use = self.net.use(h).flatten() > 0
        result = torch.full((len(h),), -1, dtype=torch.long)
        bits = F.linear(h[use], bw, bb) > 0
        result[use] = table[(bits.long() * self.powers[: len(bw)]).sum(1)]
        counts["use_logits"] += len(h)
        counts["address_bits"] += bits.numel()
        return result


class Dispatch:
    """Prepare the per-rule eligible interfaces once before admission opens."""

    def __init__(self, cat, out, mode, fraction, recognizer):
        from time import perf_counter

        tick = perf_counter()
        self.mode = mode
        self.full = recognizer
        self.menus = {}
        self.compiled = {}
        self.router = Router(cat, out, mode) if mode in ("direct", "sparse") else None
        if mode == "tree":
            from tree_routing import TreeRouter

            self.router = TreeRouter(cat, out)
        for rule, items in cat.by.items():
            legal = [
                i
                for i in items
                if all(j == g for j, (_, g, _) in enumerate(cat.units[i]))
            ]
            menu = legal[: math.ceil(len(legal) * fraction)]
            if menu:
                self.menus[rule] = menu
                self.compiled[rule] = (
                    self.router.prepare(menu)
                    if self.router
                    else (torch.tensor(menu), cat.codes[menu])
                )
        self.setup = perf_counter() - tick

    def select(self, rule, x, counts):
        arg = self.compiled[rule]
        if self.router:
            return self.router.select(x, arg, counts)
        ids, code = arg
        scores = self.full(x[:, None, :], code[None, :, :])
        a, i = scores.max(1)
        counts["recognition_scores"] += scores.numel()
        counts["route_inputs"] += len(x)
        return torch.where(a > 0, ids[i], -1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("donor", type=Path)
    p.add_argument("--tree", action="store_true")
    a = p.parse_args()
    torch.set_num_threads(1)
    if a.tree:
        from tree_routing import fit as fit_tree

        fit_tree(a.root, a.out, a.donor)
    else:
        fit(a.root, a.out, a.donor)
