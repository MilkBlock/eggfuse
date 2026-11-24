"""Teach useful instruction sequences in event-selected role order from teacher receipts."""

import argparse, json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F
from benefit_policy import BenefitNet
from event_addresses import Directory
from protocol_experiment import dump
from protocol_model import decode
from recursive_agent import Reader
from recursive_train import folder, keys, read
from txn_policy import plans


def labels(d, root, net):
    rd = Reader(read(d / "program.json"), root, rename_seed=9037)
    mem = Directory(rd, Counter())
    byrun = defaultdict(list)
    for q in read(d / "tape.json")["requests"]:
        byrun[q["run"]].append(q)
    cache = {}
    gain = defaultdict(Counter)
    count = Counter()
    for frame in map(json.loads, (d / "memory.jsonl").open()):
        rd.advance(frame)
        rules = dict(frame["rules"])
        for q in byrun[frame["run"]]:
            r = q["rule"]
            if not any("primitive" in x["call"] for x in rd.iface.rules[r]["query"]):
                continue
            refs = [(rd.store.alias(t), pc) for t, pc in keys(q)]
            for j, a in enumerate(refs):
                if rd.store.visible[a]["version"] < rules[r]:
                    continue
                order = mem.order(r, j)
                positions = np.array(
                    [[mem.bank(mem.roles[r][k]).positions[refs[k]] for k in order]]
                )
                for depth, dest in enumerate(order[1:], 1):
                    context = r, order, depth
                    if context not in cache:
                        cache[context] = plans(rd, r, depth, True, order=order)
                    if not cache[context]:
                        continue
                    _, _, n = mem.window(r, order[:depth], dest, positions[:, :depth])
                    b = mem.bank(mem.roles[r][dest])
                    for plan in cache[context]:
                        col = plan.output_column
                        _, offsets = b.postings(col)
                        code = b.codes[positions[0, depth], col]
                        after = offsets[code + 1] - offsets[code]
                        gain[context][plan] += int(n[0] - after) - len(plan.steps)
                        count[context] += 1
    actions = []
    operands = []
    used = Counter()
    for (r, order, depth), scores in gain.items():
        best = max(scores, key=scores.get)
        teacher = best.steps if scores[best] > 0 else ()
        used[len(teacher)] += count[r, order, depth]
        decode(
            net,
            rd,
            r,
            depth,
            256,
            Counter(),
            example=(teacher, actions, operands),
            order=order,
        )
    return actions, operands, dict(used)


def fit(root, out):
    torch.manual_seed(55191)
    net = BenefitNet()
    net.load_state_dict(
        torch.load(
            Path("run-recall/computation-benefit/residual.pt"), weights_only=True
        )
    )
    counts = {}
    actions = []
    operands = []
    for case in (
        "loopfact",
        "grammar-17118",
        "grammar-17119",
        "grammar-benefit-left-17118",
        "grammar-benefit-large-fork-17120",
        "grammar-benefit-large-twice-17120",
    ):
        a, o, c = labels(folder(root, case), root, net)
        actions += a
        operands += o
        counts[case] = c
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    net.to(dev)
    opt = torch.optim.AdamW(
        list(net.instruction.parameters()) + list(net.operand.parameters()), lr=0.0008
    )

    def pack(rows):
        xs, ys = zip(*rows)
        lengths = torch.tensor([len(x) for x in xs])
        p = torch.nn.utils.rnn.pad_sequence(xs, batch_first=True)
        return (
            p.to(dev),
            (torch.arange(p.shape[1])[None, :] >= lengths[:, None]).to(dev),
            torch.tensor(ys, device=dev),
        )

    pools = [(net.instruction, *pack(actions))]
    if operands:
        pools.append((net.operand, *pack(operands)))
    for _ in range(260):
        loss = 0
        for head, x, mask, y in pools:
            ix = torch.randint(len(x), (64,), device=dev)
            loss += F.cross_entropy(
                head(x[ix]).squeeze(-1).masked_fill(mask[ix], -1.0e4), y[ix]
            )
        opt.zero_grad()
        loss.backward()
        opt.step()
    torch.save(
        {
            k: v
            for k, v in net.cpu().state_dict().items()
            if k.startswith(("operand.", "instruction."))
        },
        out / "computation.pt",
    )
    dump(
        out / "computation-fit.json",
        dict(
            steps=260,
            seed=55191,
            device=dev,
            source_examples=counts,
            instruction_examples=len(actions),
            operand_examples=len(operands),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for arg in ("root", "out"):
        p.add_argument(arg, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    fit(a.root, a.out)
