"""Primitive and compiled alternatives share B's event-conditioned terminal score."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
from event_addresses import Directory
from event_templates import BranchNet, shape
from int_parameters import link_layouts
from receipt_bake import read, save
from recursive_agent import Reader
from train_ripsat import layout_id


class Family:
    def __init__(self, rd, program, catalog):
        self.units = dict(link_layouts(program, catalog))
        self.menu = defaultdict(list)
        self.codes = {}
        self.held = {
            i
            for i, u in enumerate(catalog["layouts"])
            if int(layout_id(u)[:8], 16) % 5 == 0
        }
        for i, u in self.units.items():
            self.menu[u[0][0]].append(i)
        for r, ids in self.menu.items():
            for j in range(len(rd.iface.roles[r])) if rd.iface.roles[r] else (-1,):
                root = shape(rd, r, j)
                code = []
                for i in [-1, *ids]:
                    u = [] if i < 0 else self.units[i][1:]
                    # First vector describes the entry. The second describes
                    # downstream operations; the last two scalars describe wiring.
                    parts = [shape(rd, rid, 0 if w else -1) for rid, _, w in u]
                    rest = np.mean(parts, axis=0) if parts else root
                    code.append(
                        [
                            *root,
                            *rest,
                            np.log1p(1 + len(u)) / 8,
                            sum(owner >= 0 for _, _, w in u for owner, _ in w) / 12,
                        ]
                    )
                self.codes[r, j] = np.asarray(code, np.float32)


def scores(model, event, codes):
    n, e = len(event), len(codes)
    x = torch.cat(
        (event[:, None, :].expand(-1, e, -1), codes[None, :, :].expand(n, -1, -1)),
        dim=-1,
    )
    return model(x).squeeze(-1)


def samples(data, folder, store, name, seed, training, *, held_masks=None):
    program = read(folder / "program.json")
    rd = Reader(program, data, rename_seed=seed)
    family = Family(rd, program, read(store / "catalog.json"))
    mem = Directory(rd, Counter())
    byrun = defaultdict(list)
    for q in read(folder / "tape.json")["requests"]:
        byrun[q["run"]].append(q)
    support = defaultdict(dict)
    for uid, occs in read(store / (name + "-occasions.json")).items():
        uid = int(uid)
        for ts in occs:
            support[ts[0]][uid] = len(ts) - 1
    groups = defaultdict(list)
    rng = np.random.default_rng(seed)
    for f in map(json.loads, (folder / "memory.jsonl").open()):
        rd.advance(f)
        labels = defaultdict(dict)
        wm = dict(f["rules"])
        for q in byrun[f["run"]]:
            r = q["rule"]
            if r not in family.menu:
                continue
            for j, p in enumerate(q["parents"]):
                a = rd.store.alias(p["address"]["token"]), p["address"]["op"]
                bank = mem.bank(mem.roles[r][j])
                if bank.rows[bank.positions[a], 2] >= wm[r]:
                    labels[r, j, bank.positions[a]].update(support[q["token"]])
            if not q["parents"]:
                labels[r, -1, 0].update(support[q["token"]])
        for r, j, ix in mem.events(wm):
            if r not in family.menu:
                continue
            for k in ix:
                wanted = labels.get((r, j, k), {})
                if not wanted and rng.random() > 0.04:
                    continue
                vec = (
                    np.zeros(16, np.float32)
                    if j < 0
                    else mem.bank(mem.roles[r][j]).vec[k].copy()
                )
                choices = [
                    (n, uid)
                    for n, uid in enumerate(family.menu[r], 1)
                    if not training or uid not in family.held
                ]
                if not choices:
                    continue
                y = [max(wanted.get(uid, 0), 0) for _, uid in choices]
                if training and not any(y) and wanted:
                    continue
                groups[r, j].append((vec, [0 if any(y) else 1, *y]))
    batches = []
    for (r, j), vs in groups.items():
        pick = [
            0,
            *[
                k
                for k, uid in enumerate(family.menu[r], 1)
                if not training or uid not in family.held
            ],
        ]
        if held_masks is not None:
            held_masks.append(
                torch.tensor(
                    [k > 0 and family.menu[r][k - 1] in family.held for k in pick]
                )
            )
        batches.append(
            (
                torch.tensor(np.stack([x for x, _ in vs])),
                torch.tensor(family.codes[r, j][pick]),
                torch.tensor([y for _, y in vs], dtype=torch.float32),
            )
        )
    return batches


def train(data, root, out):
    torch.manual_seed(4021)
    model = BranchNet()
    model.load_state_dict(
        torch.load("run-recall/cell-events/template.pt", weights_only=True)
    )
    batches = samples(data, root / "sum", out, "sum", 415, True)
    valid = samples(data, root / "dot", out, "dot", 426, False)
    optim = torch.optim.AdamW(model.parameters(), lr=0.001)

    def metrics(groups):
        good = useful = n = pos = 0
        with torch.no_grad():
            for x, c, y in groups:
                s = scores(model, x, c)
                k = s.argmax(1)
                good += (y.gather(1, k[:, None]) > 0).sum().item()
                useful += (
                    ((k > 0) & (y.gather(1, k[:, None]).flatten() > 0)).sum().item()
                )
                n += len(x)
                pos += int((y[:, 0] == 0).sum())
        return dict(rows=n, compatible=good, useful=useful, positive=pos)

    before = metrics(valid)
    for _ in range(16):
        for g in torch.randperm(len(batches)):
            x, c, y = batches[g]
            for batch in torch.randperm(len(y)).split(128):
                score = scores(model, x[batch], c)
                target = y[batch]
                target = target / target.sum(1, keepdims=True)
                loss = -(target * F.log_softmax(score, dim=1)).sum(1).mean()
                optim.zero_grad()
                loss.backward()
                optim.step()
    save(
        out / "training.json",
        dict(
            train=metrics(batches),
            validation_before=before,
            validation_after=metrics(valid),
            seed=4021,
            epochs=16,
            held=[
                i
                for i, u in enumerate(read(out / "catalog.json")["layouts"])
                if int(layout_id(u)[:8], 16) % 5 == 0
            ],
        ),
    )
    torch.save(model.state_dict(), out / "entry.pt")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("data", "root", "out"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    train(a.data, a.root, a.out)
