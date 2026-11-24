"""Train an event-conditioned GNN on 10k typed three-level-or-deeper layouts."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import torch
from torch.nn import functional as F

from anchor_set_audit import load_actor
from alternate_proofs import digest
from higher_cell import read
from large_cell_audit import root_only
from protocol_experiment import dump
from ripsat_layout import capture, signatures
from ripsat_policy import CellScorer, GraphBank
from train_ripsat import layout_id


def depth(layout):
    levels = []
    for _, _, inputs in layout:
        levels.append(1 + max((levels[i] for i, _ in inputs if i >= 0), default=0))
    return max(levels)


def deployable(layout):
    return root_only(layout) and all(
        i == group for i, (_, group, _) in enumerate(layout)
    )


def measure(roots, ids):
    touched = set()
    possible = set()
    for layouts in roots.values():
        for layout, occurrences in layouts.items():
            if layout not in ids:
                continue
            for _, ready, first, tokens in occurrences:
                if ready and first:
                    touched.update(tokens)
                    if deployable(layout):
                        possible.update(tokens)
    return dict(ready_distinct_steps=len(touched), root_boundary_steps=len(possible))


def main(root, weights, out, size, examples=None):
    import numpy as np
    from event_addresses import Directory
    from recursive_agent import Reader
    from side_boundary import address
    import json

    torch.manual_seed(1703)
    rng = np.random.default_rng(1703)
    donor = read(root / "sum/program.json")
    train = ["sum", "dot"]
    data = {
        name: capture(root / name, donor, 10, grow_consumers=True) for name in train
    }
    support, ready = Counter(), Counter()
    for _, _, roots, _ in data.values():
        for layouts in roots.values():
            for l, occ in layouts.items():
                if depth(l) >= 3 and int(layout_id(l)[:8], 16) % 8:
                    support[l] += 1
                    ready[l] += any(r and f for _, r, f, _ in occ)
    layouts = sorted(support, key=lambda l: (-ready[l], -support[l], l))[:size]
    if not 0 < size == len(layouts):
        raise ValueError("requested catalog exceeds distinct eligible training layouts")
    ids = {l: i for i, l in enumerate(layouts)}
    actor = load_actor(weights, True)
    cat = actor.catalog_type(donor)
    with torch.no_grad():
        bank = GraphBank(layouts, cat, actor.template_graph(cat).detach())
    model = CellScorer(actor.width)
    encoder = torch.nn.Linear(16, actor.width)
    opt = torch.optim.AdamW([*model.parameters(), *encoder.parameters()], lr=0.003)
    contexts, labels, indexes = [], [], []
    by_rule = defaultdict(list)
    for i, l in enumerate(layouts):
        by_rule[l[0][0]].append(i)
    for name, (refs, mapped, roots, _) in data.items():
        d = root / name
        rd = Reader(read(d / "program.json"), root, rename_seed=179)
        mem = Directory(rd, Counter())
        runs = defaultdict(list)
        for j, q in enumerate(refs):
            runs[q["run"]].append((j, q))
        for frame in map(json.loads, (d / "memory.jsonl").read_text().splitlines()):
            rd.advance(frame)
            wm = dict(frame["rules"])
            for j, q in runs[frame["run"]]:
                rid = mapped[q["rule"]]
                if not by_rule.get(rid):
                    continue
                events = []
                for p in q["parents"]:
                    t, pc = address(p)
                    a = rd.store.alias(t), pc
                    row = rd.store.visible[a]
                    if row["version"] >= wm[q["rule"]]:
                        b = mem.bank(row["table"])
                        events.append(b.vec[b.positions[a]])
                if not q["parents"]:
                    events.append(np.zeros(16, np.float32))
                observed = {
                    ids[l]: any(r and f for _, r, f, _ in occ)
                    for l, occ in roots.get(j, {}).items()
                    if l in ids
                }
                sampled = rng.choice(
                    by_rule[rid],
                    min(len(by_rule[rid]), max(1, len(observed))),
                    replace=False,
                )
                for event in events:
                    for i in observed.keys() | set(sampled):
                        contexts.append(event)
                        indexes.append(i)
                        labels.append((i in observed, observed.get(i, False)))
    x = torch.tensor(np.stack(contexts))
    y = torch.tensor(labels, dtype=torch.float32)
    indices = torch.tensor(indexes)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(dev)
    encoder.to(dev)
    # Match example and optimizer budgets across different catalog sizes.
    examples = len(x) if examples is None else examples
    if examples < len(x):
        raise ValueError("training budget would omit catalog examples")
    order = torch.cat(
        [torch.randperm(len(x)) for _ in range((examples + len(x) - 1) // len(x))]
    )[:examples]
    for batch in order.split(256):
        unique, inverse = torch.unique(indices[batch], return_inverse=True)
        codes = model.encode(bank.batch(unique, dev))
        loss = F.binary_cross_entropy_with_logits(
            model(encoder(x[batch].to(dev)), codes[inverse.to(dev)]), y[batch].to(dev)
        )
        opt.zero_grad()
        loss.backward()
        opt.step()
    model.cpu().eval()
    encoder.cpu().eval()
    out.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        torch.save(
            dict(
                model=model.state_dict(),
                encoder=encoder.state_dict(),
                codes=bank.encode(model),
            ),
            out / "event-gnn.pt",
        )
    dump(out / "catalog.json", dict(signatures=signatures(donor), layouts=layouts))
    report = dict(
        training=train,
        root_actor=digest(weights),
        depth=dict(Counter(map(depth, layouts))),
        gradient_layouts=len(set(indexes)),
        observed_gradient_layouts=len(set(indices[y[:, 0].bool()].tolist())),
        ready_gradient_layouts=len(set(indices[y[:, 1].bool()].tolist())),
        pairs=len(x),
        examples=examples,
        updates=(examples + 255) // 256,
        device=dev,
        deployable=sum(map(deployable, layouts)),
        programs={},
    )
    for name in ("fact", "loopfact", "sum-divisors"):
        refs, _, roots, _ = capture(root / name, donor, 10, grow_consumers=True)
        report["programs"][name] = dict(commits=len(refs), **measure(roots, ids))
    dump(out / "audit.json", report)
    print(report, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("root", "weights", "out"):
        p.add_argument(key, type=Path)
    p.add_argument("--size", type=int, default=10000)
    p.add_argument("--examples", type=int)
    a = p.parse_args()
    torch.set_num_threads(1)
    main(a.root, a.weights, a.out, a.size, a.examples)
