"""Native exclusive training trajectories and static decoder imitation on training programs."""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

import torch
from torch.nn import functional as F

from protocol_learning import BoundaryRecorder, LearningPolicy
from protocol_model import ProtocolNet, decode
from recursive_agent import Reader
from recursive_train import folder, read
from transaction_native import execute
from txn_policy import plans

TRAIN = (
    "grammar-17118",
    "grammar-17119",
    "grammar-stride2-17118",
    "grammar-stride3-17119",
    "loopfact",
)
VALID = "grammar-stride2-17122"


def collate(rows):
    return [torch.cat(x) for x in zip(*rows, strict=True)]


def fit(root, dest):
    dest.mkdir(exist_ok=True, parents=True)
    torch.manual_seed(39113)
    torch.set_num_threads(1)
    model = ProtocolNet().eval()
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    proof, query, ins, operand = [], [], [], []
    counts = {}
    names = random.Random(71303)
    for case in (*TRAIN, VALID):
        # Independent model trajectory, candidate proofs labeled by actual native admission.
        p = LearningPolicy(
            root,
            "B",
            model,
            collect=True,
            route="chain" if "stride" in case else "learned",
        )
        p.address_mask = names.getrandbits(63)
        execute(root, case, study=p, series="protocol-training/probe", seconds=180)
        counts[case] = [
            sum(len(x[0]) for x in p.samples),
            sum(len(x[0]) for x in p.queries),
        ]
        if case == VALID:
            valid = collate(p.samples)
            continue
        proof.extend(p.samples)
        query.extend(p.queries)
        rd = Reader(read(folder(root, case) / "program.json"), root)
        actual = Counter(
            q["rule"] for q in read(folder(root, case) / "tape.json")["requests"]
        )
        for rule in actual:
            for depth in range(1, len(rd.order(rule))):
                teachers = plans(rd, rule, depth, True)
                for teacher in [t.steps for t in teachers] or [()]:
                    decode(
                        model, rd, rule, depth, 256, Counter(), (teacher, ins, operand)
                    )
    raw, meta, state, y = [x.to(device) for x in collate(proof)]
    qr, qs, qy, scope_context = [x.to(device) for x in collate(query)]
    model.to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=0.003)
    # Balance programs' scarce confirmations by drawing positives explicitly.
    pos = torch.where(y > 0)[0]
    neg = torch.where(y == 0)[0]

    def draw(ix, n):
        return ix[torch.randint(len(ix), (n,), device=device)]

    def pack(rows):
        xs, ys = zip(*rows, strict=True)
        padded = torch.nn.utils.rnn.pad_sequence(xs, batch_first=True).to(device)
        mask = (
            torch.arange(padded.shape[1], device=device)
            < torch.tensor([len(x) for x in xs], device=device)[:, None]
        )
        return padded, mask, torch.tensor(ys, device=device)

    ix, im, iy = pack(ins)
    ox = pack(operand) if operand else None
    for _ in range(320):
        k = torch.cat((draw(pos, 96), draw(neg, 160)))
        # Small correction to the trained Compose score. Increased positive weight
        # reflects the downstream impact of a missed derivation.
        s = state[k, 0] * 8 + model.score(meta[k], model.value(raw[k]), state[k])
        loss = F.binary_cross_entropy_with_logits(s, y[k])
        k = torch.randint(len(qy), (128,), device=device)
        q = model.query(torch.cat((model.value(qr[k]), qs[k]), 1)).flatten()
        loss += F.binary_cross_entropy_with_logits(q, qy[k])
        k = torch.randint(len(iy), (96,), device=device)
        loss += F.cross_entropy(
            model.instruction(ix[k]).squeeze(-1).masked_fill(~im[k], -1e4), iy[k]
        )
        if ox:
            x, mask, t = ox
            loss += F.cross_entropy(
                model.operand(x).squeeze(-1).masked_fill(~mask, -1e4), t
            )
        opt.zero_grad()
        loss.backward()
        opt.step()
    model.cpu().eval()
    with torch.no_grad():
        r, m, s, yv = valid
        pred = s[:, 0] * 8 + model.score(m, model.value(r), s)
        validation = {
            "positive": int(yv.sum()),
            "hits": int(((pred >= 0) & (yv > 0)).sum()),
            "issued": int((pred >= 0).sum()),
        }
    records = []
    for case in TRAIN:
        p = LearningPolicy(
            root, "C", model, route="chain" if "stride" in case else "learned"
        )
        p.client_type = BoundaryRecorder
        p.record_boundaries = True
        p.address_mask = names.getrandbits(63)
        execute(root, case, study=p, series="protocol-training/boundaries", seconds=180)
        records.extend(p.boundaries)
    x = torch.stack([v[0] for v in records])
    future = torch.tensor([v[1:] for v in records], dtype=torch.float)
    # Offline rollout targets for a decision at the current checkpoint. Seal
    # sacrifices every later admission. Submit/observe trade IPC cost against
    # delaying evidence in a queue with uncertain downstream productivity.
    observe, submit = future[:, 2], future[:, 3]
    seal = (future[:, 0] == 0).float()
    targets = torch.stack((observe, submit, seal), 1)
    model.to(device)
    x, targets = x.to(device), targets.to(device)
    opt = torch.optim.AdamW(
        [*model.boundary.parameters(), *model.scope.parameters()], lr=0.004
    )
    # For observation scope, estimate the reduction in downstream query loss
    # when exposing this typed observation rather than just the status features.
    with torch.no_grad():
        observed = model.value(qr)
        full = model.query(torch.cat((observed, qs), 1)).flatten()
        masked = model.query(
            torch.cat((model.value(torch.zeros_like(qr)), qs), 1)
        ).flatten()
        benefit = F.binary_cross_entropy_with_logits(
            masked, qy, reduction="none"
        ) - F.binary_cross_entropy_with_logits(full, qy, reduction="none")
    # Scope is chosen before observing the value. Only a preceding observation
    # from the training rollout and pre-read occupancy may enter the predictor.
    with torch.no_grad():
        prior = scope_context[:, 10:]
        prior_value = model.value(prior) * (prior.abs().sum(1) > 0)[:, None]
        scope_x = torch.cat((scope_context[:, :10], prior_value), 1)
    scope_y = (benefit > 0).float()
    for _ in range(300):
        k = torch.randint(len(x), (128,), device=device)
        weights = torch.where(
            targets[k] > 0, (len(x) / targets.sum(0).clamp_min(1)).clamp_max(30), 1.0
        )
        weights[:, 2] = torch.where(targets[k, 2] > 0, 1.0, 12.0)
        loss = F.binary_cross_entropy_with_logits(
            model.boundary(x[k]), targets[k], weight=weights
        )
        j = torch.randint(len(scope_y), (128,), device=device)
        loss += F.binary_cross_entropy_with_logits(
            model.scope(scope_x[j]).flatten(), scope_y[j]
        )
        opt.zero_grad()
        loss.backward()
        opt.step()
    model.cpu().eval()
    torch.save(model.state_dict(), dest / "model.pt")
    info = {
        "device": device,
        "training_programs": TRAIN,
        "validation": VALID,
        "proof_query_samples": counts,
        "instruction_examples": len(ins),
        "ambiguous_operand_examples": len(operand),
        "boundary_samples": len(records),
        "boundary_positives": targets.sum(0).cpu().tolist(),
        "validation_proofs": validation,
        "seed": 39113,
    }
    (dest / "training.json").write_text(json.dumps(info, indent=2) + "\n")
    print(info, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("dest", type=Path)
    args = ap.parse_args()
    fit(args.root, args.dest)
