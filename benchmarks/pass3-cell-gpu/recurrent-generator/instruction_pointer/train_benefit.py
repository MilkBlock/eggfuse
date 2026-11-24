"""Fit timing and structural choices from paired execution, then compare proof updates."""

import argparse
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
import torch
from torch.nn import functional as F
from benefit_policy import BenefitNet, BenefitPolicy
from compute_pairs import TRAIN, CUTS, Probe
from protocol_experiment import dump
from protocol_model import decode
from recursive_agent import Reader
from recursive_train import folder, read
from transaction_native import execute
from txn_policy import plans


def relative_gain(slow, fast):
    # Dimensionless equal-weight relative reductions. Inclusive wall accounts
    # for CPU, feedback and transfer; the other axes measure paid work directly.
    assert slow["sha"] == fast["sha"]
    return mean(
        (slow[k] - fast[k]) / max(slow[k], fast[k], 1e-9)
        for k in ("wall", "visits", "paid", "failures")
    )


def labels(root, net, pairs):
    features = []
    rewards = []
    instructions = []
    operands = []
    records = {}
    for case in TRAIN:
        rows = pairs[case]
        rd = Reader(read(folder(root, case) / "program.json"), root)
        costs = []
        positive = 0
        for low, high in zip(CUTS, CUTS[1:]):
            a = [r for r in rows if r["cut"] == low]
            b = [r for r in rows if r["cut"] == high]
            if a[0]["sha"] != b[0]["sha"]:
                costs.append(dict(interval=[low, high], comparable=False))
                continue
            g = mean(relative_gain(y, x) for x, y in zip(a, b, strict=True))
            costs.append(dict(interval=[low, high], comparable=True, gain=g))
            positive = max(positive, g)
            for *x, n in a[0]["features"]:
                if low < round(math.expm1(x[1])) <= high:
                    for _ in range(min(32, n)):
                        features.append(x)
                        rewards.append(g)
        # Only observed programs that paid off on at least one interval receive
        # structure credit. Names and dynamic handles never enter the decoder.
        ins = []
        ops = []
        executed = {(r, pc) for r, k, pc, n in rows[0]["issued_plan_counts"]}
        for rule in sorted({r for r, _ in executed}):
            for depth in range(1, len(rd.order(rule))):
                for p in plans(rd, rule, depth, True):
                    if (rule, p.atom) in executed and positive > 0:
                        decode(
                            net, rd, rule, depth, 256, Counter(), (p.steps, ins, ops)
                        )
        for _ in range(max(1, round(8 * positive))):
            instructions += ins
            operands += ops
        records[case] = dict(
            intervals=costs,
            instructions=len(ins),
            ambiguous=len(ops),
            rollouts=[{k: v for k, v in r.items() if k != "features"} for r in rows],
        )
        if ops:
            # Same-type operand substitutions give executable counterfactual
            # programs. Compare cost only when the end state is identical.
            alt = Probe(root, 0)
            alt.alternate = True
            m = execute(
                root,
                case,
                study=alt,
                series="benefit-training/alternative",
                seconds=180,
            )
            baseline = rows[0]
            equal = m["state_sha"] == baseline["sha"]
            records[case]["alternative"] = dict(
                equal_state=equal,
                sha=m["state_sha"],
                paid=m["paid"],
                wall=m["wall"],
                visits=m["work"]["visits"],
                accepted=m["committed_tokens"],
                signed=m["signed_ops"],
            )
            if (
                not equal
                and baseline["sha"]
                == read(folder(root, case) / "capture.json")["state_sha"]
            ):
                # Additional operand preference only when the original
                # reaches the reference and the substitution loses it.
                operands += ops
    return (
        torch.tensor(features),
        torch.tensor(rewards),
        instructions,
        operands,
        records,
    )


def padded(rows, device):
    xs, ys = zip(*rows, strict=True)
    x = torch.nn.utils.rnn.pad_sequence(xs, batch_first=True).to(device)
    mask = (
        torch.arange(x.shape[1], device=device)[None, :]
        < torch.tensor([len(v) for v in xs], device=device)[:, None]
    )
    return x, mask, torch.tensor(ys, device=device)


def train(root, out, pairs_file=None):
    torch.set_num_threads(1)
    torch.manual_seed(49177)
    out.mkdir(exist_ok=True, parents=True)
    net = BenefitNet()
    net.compose.load_state_dict(
        torch.load(root / "recursive-agent/multi.pt", weights_only=True)
    )
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    pairs = (
        read(pairs_file)
        if pairs_file
        else {name: read(root / "benefit-pairs" / (name + ".json")) for name in TRAIN}
    )
    dump(out / "paired-inputs.json", pairs)
    x, y, ins, ops, records = labels(root, net, pairs)
    raw = []
    for i, case in enumerate(TRAIN):
        s = BenefitPolicy(root, net.eval(), "residual", collect=True)
        s.address_mask = 159557 * (i + 1)
        m = execute(root, case, study=s, series="benefit-training/proof", seconds=180)
        assert m["termination"] == "schedule_end"
        raw += s.examples
    by = defaultdict(list)
    for row in raw:
        by[row[1].shape[1]].append(row)
    banks = {
        d: [torch.cat(v).to(dev) for v in zip(*rows, strict=True)]
        for d, rows in by.items()
    }
    a, b = padded(ins, dev), padded(ops, dev)
    x, y = x.to(dev), y.to(dev)
    net.to(dev)
    opt = torch.optim.AdamW(
        [
            *net.timing.parameters(),
            *net.instruction.parameters(),
            *net.operand.parameters(),
        ],
        lr=0.003,
    )
    for _ in range(420):
        ix = torch.randint(len(y), (128,), device=dev)
        loss = F.mse_loss(net.timing(x[ix]).flatten(), y[ix])
        for (data, mask, target), head in ((a, net.instruction), (b, net.operand)):
            ix = torch.randint(len(target), (64,), device=dev)
            loss += F.cross_entropy(
                head(data[ix]).squeeze(-1).masked_fill(~mask[ix], -1e4), target[ix]
            )
        opt.zero_grad()
        loss.backward()
        opt.step()
    import copy

    fits = {}
    for arm in ("residual", "full"):
        torch.manual_seed(49178)
        model = copy.deepcopy(net)
        model.compose.requires_grad_(arm == "full")
        prm = [*model.value.parameters(), *model.correction.parameters()]
        if arm == "full":
            prm += list(model.compose.parameters())
        opt = torch.optim.AdamW(prm, lr=0.001)
        depths = sorted(banks)
        pos = {d: torch.where(banks[d][3])[0] for d in depths}
        for step in range(400):
            d = depths[step % len(depths)]
            meta, seq, rawval, target, prior = banks[d]
            ix = torch.randint(len(target), (96,), device=dev)
            if len(pos[d]):
                ix = torch.cat(
                    (ix, pos[d][torch.randint(len(pos[d]), (32,), device=dev)])
                )
            h = model.compose.start(meta[ix])
            for j in range(d):
                val, h = model.compose(h, seq[ix, j])
            score = model.prediction(
                meta[ix], h, rawval[ix], val, rawval[ix, :6].sum(1), arm
            )
            loss = F.binary_cross_entropy_with_logits(score, target[ix].float())
            opt.zero_grad()
            loss.backward()
            opt.step()
        torch.save(model.cpu().state_dict(), out / (arm + ".pt"))
        fits[arm] = sum(v.numel() for v in prm)
    dump(
        out / "training.json",
        dict(
            device=dev,
            seed=49177,
            train=TRAIN,
            interval_examples=len(y),
            weighted_instruction_rows=len(ins),
            weighted_operand_rows=len(ops),
            proof_examples=sum(len(v[3]) for v in banks.values()),
            proof_trainable=fits,
            cases=records,
        ),
    )
    print(dev, len(y), len(ins), len(ops), fits, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--paired-inputs", type=Path)
    a = p.parse_args()
    train(a.root, a.out, a.paired_inputs)
