"""Expose all verified targets, amortizing complete CE over shared training prefixes."""

import json
import os
import random
from collections import Counter
from time import perf_counter

import torch

from int_parameters import StructuralBake, digest
from joint_cell_corpus import folder
from joint_cell_train import build, fitted, legacy_examples
from partner_index_worlds import args


def complete_ce(n, w, m, targets):
    root = {rid: m["root_lp"][i] for i, rid in enumerate(m["families"])}
    conditional = {}
    variants = {}
    losses = []
    for tid, refs in targets:
        rid = w.layouts[tid][0][0]
        ix = tuple(m["pos"][r] for r in refs)
        first = ix[0] if ix else None
        family = (rid, first)
        if family not in variants:
            variants[family] = n.variant_prob(w, m, rid, first)
        lp = (
            root[rid] + variants[family][m["families"][rid].index(m["menu"].index(tid))]
        )
        for j, i in enumerate(ix):
            addr = (rid if not j else tid, ix[:j])
            if addr not in conditional:
                conditional[addr] = n.address(w, m, *addr)
            lp = lp + conditional[addr][i]
        losses.append(-lp)
    return torch.stack(losses).mean()


def train(a, held):
    d = folder(a)
    shell = fitted(a, held, "sweep", 0)
    groups = build(a, held, shell)
    groups["legacy"] = legacy_examples(a, shell)
    worlds = {id(w): w for rows in groups.values() for w, _, _ in rows}
    shape = {i: StructuralBake(w.prog) for i, w in worlds.items()}
    signatures = set()
    state_targets = {}
    inventory = Counter()
    arities = Counter()
    for src, rows in groups.items():
        for w, s, ts in rows:
            key = (str(w.dir), digest(s))
            if key not in state_targets:
                state_targets[key] = (w, s, set())
            state_targets[key][2].update(ts)
            for tid, refs in ts:
                inventory[src] += 1
                arities[len(refs)] += 1
                signatures.add(shape[id(w)].key(w.layouts[tid]))
    data = [(w, s, sorted(ts)) for w, s, ts in state_targets.values()]
    total = sum(len(ts) for _, _, ts in data)
    (d / f"{held}-inventory.json").write_text(
        json.dumps(
            dict(
                states=len(data),
                unique_targets=total,
                sources=inventory,
                arity=arities,
                signatures=sorted(signatures),
            )
        )
    )
    for seed in (71, 113):
        dest = d / f"{held}-sweep-{seed}"
        if dest.with_suffix(".json").exists():
            continue
        n = fitted(a, held, "sweep", 0)
        n.grouped_training_reduction = True
        opt = torch.optim.AdamW(
            [p for p in n.parameters() if p.requires_grad], lr=0.001, weight_decay=0
        )
        rng = random.Random(seed)
        indices = list(range(len(data)))
        curve = []
        exposures = 0
        steps = 0
        start = perf_counter()
        for epoch in range(2):
            rng.shuffle(indices)
            ce = 0.0
            for i in indices:
                w, s, ts = data[i]
                n.prepare(w)
                m = n.state(w, s)
                loss = complete_ce(n, w, m, ts)
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(n.parameters(), 2.0)
                opt.step()
                exposures += len(ts)
                steps += 1
                ce += float(loss.detach()) * len(ts)
            curve.append(
                dict(
                    epoch=epoch + 1,
                    loss=ce / total,
                    steps=steps,
                    exposures=exposures,
                    seconds=perf_counter() - start,
                )
            )
            print(held, seed, curve[-1], flush=True)
        torch.save(
            {k: p.detach() for k, p in n.named_parameters() if p.requires_grad},
            dest.with_suffix(".pt"),
        )
        dest.with_suffix(".json").write_text(
            json.dumps(
                dict(
                    curve=curve,
                    states=len(data),
                    targets=total,
                    exposures=exposures,
                    seconds=perf_counter() - start,
                )
            )
        )


if __name__ == "__main__":
    torch.set_num_threads(1)
    train(args(), os.environ["TR_CASE"])
