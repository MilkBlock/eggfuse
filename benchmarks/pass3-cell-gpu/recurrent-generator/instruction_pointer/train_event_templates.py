"""Train the Cell-to-template address tree; tune admission on untouched validation tapes."""

import argparse, json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
from event_addresses import Directory
from event_templates import BranchNet, TemplateTree
from protocol_experiment import dump
from recursive_agent import Reader
from recursive_train import read, keys, folder


def rows(root, d, seed):
    rd = Reader(read(d / "program.json"), root, rename_seed=seed)
    mem = Directory(rd, Counter())
    tree = TemplateTree(rd)
    byrun = defaultdict(list)
    for q in read(d / "tape.json")["requests"]:
        byrun[q["run"]].append(q)
    x = []
    y = []
    boot = []
    rng = np.random.default_rng(seed)
    for f in map(json.loads, (d / "memory.jsonl").open()):
        rd.advance(f)
        rules = dict(f["rules"])
        label = defaultdict(set)
        for q in byrun[f["run"]]:
            r = q["rule"]
            parents = keys(q)
            if not parents:
                label[-1, 0].add((r, -1))
            for j, (tok, op) in enumerate(parents):
                a = rd.store.alias(tok), op
                row = rd.store.visible[a]
                if row["version"] >= rules[r]:
                    tab = row["table"]
                    label[tab, mem.bank(tab).positions[a]].add((r, j))
        for t, root_node, ix, h, ver in tree.blocks(mem, rules):
            for k, i in enumerate(ix):
                wanted = label.get((t, i), set())
                if not wanted and t >= 0 and rng.random() > 0.08:
                    continue
                todo = [root_node]
                while todo:
                    node = todo.pop()
                    if ver[k] < tree.minimum[node]:
                        continue
                    yes = not node.labels.isdisjoint(wanted)
                    x.append(np.r_[h[k], node.code])
                    y.append(yes)
                    boot.append(t < 0)
                    if yes:
                        todo.extend(node.children)
    return np.asarray(x, np.float32), np.asarray(y, np.float32), np.asarray(boot)


def fit(root, out, donor, dot):
    train = [
        donor,
        folder(root, "loopfact"),
        folder(root, "grammar-17118"),
        folder(root, "grammar-17119"),
    ]
    validation = [dot, folder(root, "grammar-17120")]
    a = [rows(root, d, 4341 + i) for i, d in enumerate(train)]
    torch.manual_seed(4951)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    x, y = [
        torch.from_numpy(np.concatenate([part[i] for part in a])).to(dev)
        for i in (0, 1)
    ]
    net = BranchNet().to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=0.003)
    pos = torch.where(y > 0)[0]
    for _ in range(700):
        ix = torch.cat(
            [
                torch.randint(len(y), (192,), device=dev),
                pos[torch.randint(len(pos), (64,), device=dev)],
            ]
        )
        loss = F.binary_cross_entropy_with_logits(net(x[ix]).flatten(), y[ix])
        opt.zero_grad()
        loss.backward()
        opt.step()
    net.cpu().eval()
    torch.save(net.state_dict(), out / "template.pt")
    b = [rows(root, d, 4921 + i) for i, d in enumerate(validation)]
    xv, yv, boot = map(np.concatenate, zip(*b))
    with torch.no_grad():
        v = net(torch.from_numpy(xv)).flatten().numpy()
    cuts = {}
    for name, mask in [("boot", boot), ("cell", ~boot)]:
        positive = np.sort(v[mask & (yv > 0)])
        rank = int(0.01 * (len(positive) + 1))
        cuts[name] = float(positive[rank - 1]) if rank else None
    dump(
        out / "template-fit.json",
        dict(
            cuts=cuts,
            seed=4951,
            device=dev,
            steps=700,
            train={d.name: [len(t[1]), int(t[1].sum())] for d, t in zip(train, a)},
            validation={
                d.name: [len(t[1]), int(t[1].sum())] for d, t in zip(validation, b)
            },
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for n in ("root", "out", "donor", "dot"):
        p.add_argument(n, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    fit(a.root, a.out, a.donor, a.dot)
