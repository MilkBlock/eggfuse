"""Fit on native hard negatives from training programs and compare exclusive policies."""

import argparse
import json
from pathlib import Path

import torch
from torch.nn import functional as F

from recursive_train import TRAIN
from stream_guard import JointReadout, Study
from stream_native import execute

VALID = "grammar-17122"


def collect(root, case, limit):
    study = Study(collect=True)
    result = execute(
        root,
        case,
        "stream",
        180,
        "multi",
        limit=limit,
        series="guard-training",
        study=study,
    )
    if result["termination"] == "wall_budget":
        raise RuntimeError("censored collection")
    if study.pending:
        raise RuntimeError("unmatched features at the end of the native trajectory")
    return torch.stack(study.data), torch.tensor(study.labels), dict(study.counts)


def fit(root):
    torch.manual_seed(32197)
    (root / "guard-study").mkdir(parents=True, exist_ok=True)
    folder = root / "guard-study"
    xx = []
    yy = []
    records = {}
    for case in TRAIN:
        x, y, records[case] = collect(
            root, case, 100 if not case.startswith("grammar-") else None
        )
        xx.append(x)
        yy.append(y)
    vx, vy, records[VALID] = collect(root, VALID, None)
    x = torch.cat(xx)
    y = torch.cat(yy)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    x = x.to(device)
    y = y.to(device)
    positives = torch.where(y)[0]
    negatives = torch.where(~y)[0]
    head = JointReadout().to(device)
    opt = torch.optim.AdamW(head.parameters(), lr=0.001)
    for _ in range(300):
        ix = torch.cat(
            [v[torch.randint(len(v), (128,))] for v in (positives, negatives)]
        )
        scores = head(x[ix]).flatten()
        loss = F.binary_cross_entropy_with_logits(scores, y[ix].float())
        opt.zero_grad()
        loss.backward()
        opt.step()
    head.cpu().eval()
    with torch.no_grad():
        scores = head(vx).flatten()
    config = {}
    for name, q in (("recall", 0.0), ("balanced", 0.05)):
        t = float(torch.quantile(scores[vy], q)) - 1e-5
        config[name] = dict(
            threshold=t,
            valid_total=int(vy.sum()),
            valid_kept=int(((scores >= t) & vy).sum()),
            negative_total=int((~vy).sum()),
            negative_kept=int(((scores >= t) & ~vy).sum()),
        )
    torch.save(head.state_dict(), folder / "joint.pt")
    (folder / "training.json").write_text(
        json.dumps(
            dict(
                device=device,
                training=TRAIN,
                validation=VALID,
                records=records,
                operating_points=config,
                steps=300,
            ),
            indent=2,
        )
    )


def evaluate(root, case, arm, seconds):
    folder = root / "guard-study"
    head = None
    t = 0.0
    if arm.endswith(("recall", "balanced")):
        head = JointReadout().eval()
        head.load_state_dict(torch.load(folder / "joint.pt", weights_only=True))
        t = json.loads((folder / "training.json").read_text())["operating_points"][
            arm.split("-")[-1]
        ]["threshold"]
    bits = int(arm[1]) if arm.startswith(("s", "p")) else 0
    return execute(
        root,
        case,
        "stream",
        seconds,
        "multi",
        series="guard-" + arm,
        study=Study(
            bits,
            head,
            t,
            symmetric=arm.startswith("p"),
            delta_buckets=arm.endswith("-delta"),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument(
        "arm",
        choices=(
            "fit",
            "control",
            "joint-recall",
            "joint-balanced",
            "s8",
            "s4",
            "s4-recall",
            "p4",
            "p8",
            "p8-delta",
        ),
    )
    p.add_argument("cases", nargs="*")
    p.add_argument("--seconds", type=float, default=45)
    a = p.parse_args()
    torch.set_num_threads(1)
    root = a.root.resolve()
    if a.arm == "fit":
        fit(root)
    else:
        for c in a.cases:
            d = evaluate(root, c, a.arm, a.seconds)
            print(c, a.arm, d["paid"], d["exact_endpoint"], d["wall"], flush=True)
