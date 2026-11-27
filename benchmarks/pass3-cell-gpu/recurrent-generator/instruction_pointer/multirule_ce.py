"""Full Cell Token CE. The learned gate and address MLP share the actual sampling law."""

import pickle

import numpy as np
import torch

import head_joint_index as joint
from binding_model import collate, tensor
from completion_context import write
from multirule_support import logits
from partner_index import EXPLORE
from partner_index_worlds import args, frozen
from selective_kernel import pack


@torch.no_grad()
def prep(model, ex):
    ex = dict(ex)
    ex["features"] = tuple(t.to("mps") for t in ex["features"])
    ex["gold"] = tensor(np.array(ex["g"], dtype=np.int64))
    z = ex.pop("z")
    if not z:
        return ex
    try:
        data = pack([z]) if len(z["banks"]) >= 2 else None
    except ValueError as err:
        if str(err) != "requires exactly one earlier connected role per child":
            raise
        data = None
    if data is None:
        ex["fallback"] = collate([z])
        return ex
    inp, layout = data
    _, edges = joint.prepare(model, data)
    root = inp[0].new_zeros(inp[3][0][0].shape[:2])
    cond = np.zeros(len(ex["g"]))
    for j, ((parent, _), edge) in enumerate(zip(layout, edges, strict=True), 1):
        mass = edge.mass.sum(-1)
        if parent == 0:
            root += (mass + 1e-12).log()
        # Offline teacher forcing: sum integer posting mass for the named target
        # only. This includes all channel aliases and the public-domain fallback.
        ends = edge.index.ends[0].cpu().numpy()
        owner = edge.index.owners[0].cpu().numpy()
        increments = np.diff(ends)
        for row, ids in enumerate(ex["g"]):
            r = ids[parent]
            b = ids[j]
            n = len(z["banks"][j]["row"])
            start = edge.start[0, r].cpu().numpy()
            count = edge.count[0, r].cpu().numpy()
            channel = edge.mass[0, r].cpu().numpy().astype(float)
            prob = 1 / n
            if channel.sum() > 0:
                w = np.flatnonzero((owner == b) & (increments > 0))
                units = (
                    increments[w, None]
                    * ((ends[w, None] >= start) & (ends[w, None] < start + count))
                ).sum(0)
                law = (channel / channel.sum() * units / count.clip(min=1)).sum()
                prob = (1 - EXPLORE) * law + EXPLORE / n
            cond[row] += np.log(prob)
    ex.update(inputs=inp, root=root, cond=tensor(cond.astype(np.float32)))
    return ex


def loss(model, ex, arm):
    net = model.local.base
    rule = -logits(net, ex["features"], arm).log_softmax(0)[ex["target"]]
    gold = ex["gold"]
    if "fallback" in ex:
        lp, _ = net(ex["fallback"], teacher=gold[None])
        return rule - sum(
            v[0].gather(-1, gold[:, j, None]).mean() for j, v in enumerate(lp)
        )
    if "root" in ex:
        p = (model.local.root_prior(ex["inputs"]) + ex["root"]).softmax(-1)
        p = p * (1 - EXPLORE) + EXPLORE / p.size(1)
        return rule - (p[0, gold[:, 0]].log() + ex["cond"]).mean()
    return rule


def train(a):
    seed = a.seeds[0]
    init = frozen(a, seed)
    corpus = []
    for f in sorted((a.out / "corpus").glob("*/examples.pkl")):
        with f.open("rb") as rd:
            corpus.extend(prep(init, x) for x in pickle.load(rd))
    curves = []
    for case in ("sum-divisors", "fact", "loopfact"):
        held = [x for x in corpus if x["case"].removeprefix("rollout-") == case]
        train = [x for x in corpus if x["case"].removeprefix("rollout-") != case]
        cut = np.quantile([x["owners"] for x in train], [0.2, 0.6])
        for arm in ("ce-base", "ce-count", "ce-support"):
            m = frozen(a, seed)
            m.requires_grad_(False)
            m.local.base.gate.requires_grad_(True)
            m.local.base.scorer.requires_grad_(True)
            opt = torch.optim.Adam(
                [p for p in m.parameters() if p.requires_grad], lr=0.0007
            )
            rng = np.random.default_rng(seed)
            seen = set()
            exposures = 0
            for step in range(401):
                if step in (0, 100, 400):
                    with torch.no_grad():
                        row = {
                            "case": case,
                            "arm": arm,
                            "steps": step,
                            "tokens": exposures,
                            "groups_seen": len(seen),
                        }
                        for name, items in (("training", train), ("held", held)):
                            row[name] = float(
                                torch.stack(
                                    [loss(m, x, arm).detach() for x in items]
                                ).mean()
                            )
                        curves.append(row)
                    print(row, flush=True)
                if step == 400:
                    break
                pool = [
                    i
                    for i, x in enumerate(train)
                    if step >= 160 or x["owners"] <= (cut[0] if step < 64 else cut[1])
                ]
                batch = rng.choice(pool, 4, replace=False)
                total = torch.stack([loss(m, train[i], arm) for i in batch]).mean()
                opt.zero_grad()
                total.backward()
                torch.nn.utils.clip_grad_norm_(m.parameters(), 5)
                opt.step()
                exposures += sum(len(train[i]["g"]) for i in batch)
                seen.update(batch)
            torch.save(m.state_dict(), a.out / f"{case}-{arm}.pt")
            write(a.out / "curves.json", curves)


if __name__ == "__main__":
    torch.set_num_threads(1)
    train(args())
