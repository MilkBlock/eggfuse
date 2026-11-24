"""Held-out supervision quality and collisions on the tested neural field addresses."""

import argparse, json
from collections import Counter, defaultdict
from pathlib import Path
import torch
from completion_training import Completion, labels
from recursive_agent import Reader
from recursive_train import folder, read
from protocol_experiment import dump


@torch.no_grad()
def assess(root, out, case):
    x, y, counts = labels(root, case, 72911)
    model = Completion().eval()
    model.load_state_dict(torch.load(out / "continuation.pt", weights_only=True))
    pred = model(x)
    known = y[:, 0] >= 0
    labels_known = y[known, 0]
    prob = pred[known, 0].sigmoid()
    order = prob.argsort(descending=True)
    sorted_y = labels_known[order]
    precision = sorted_y.cumsum(0) / torch.arange(1, len(sorted_y) + 1)

    def error(col, valid):
        p = pred[valid, col].clamp(0, 15)
        target = y[valid, 1 if col == 1 else 3]
        return dict(
            samples=len(p),
            log_mae=float((p - target).abs().mean()),
            mean_target=float(torch.expm1(target).mean()),
            mean_pred=float(torch.expm1(p).mean()),
        )

    d = folder(root, case)
    rd = Reader(read(d / "program.json"), root)
    by = defaultdict(list)
    for q in read(d / "tape.json")["requests"]:
        by[q["run"]].append(q)
    checked = Counter()
    planes = torch.randn(24, 8, generator=torch.Generator().manual_seed(10219))
    for f in map(json.loads, (d / "memory.jsonl").open()):
        rd.advance(f)
        for q in by[f["run"]]:
            order = rd.order(q["rule"])
            ports = [(p["address"]["token"], p["address"]["op"]) for p in q["parents"]]
            for j, r in enumerate(order):
                links = rd.iface.links(q["rule"], order[:j], (r,))
                if not len(links):
                    continue
                a, c, _, dcol = links[0]
                left = rd.index.rows[ports[a]][2][c]
                right = rd.index.rows[ports[r]][2][dcol]
                if len(links) > 1:
                    a2, c2, _, d2 = links[1]
                    lhs = rd.index.rows[ports[a2]][2][c2]
                    rhs = rd.index.rows[ports[r]][2][d2]
                else:
                    keys = torch.stack(
                        (rd.index.keys[ports[a]][c], rd.index.keys[ports[r]][dcol])
                    )
                    lhs, rhs = (
                        ((keys @ planes >= 0).long() * (2 ** torch.arange(8)))
                        .sum(1)
                        .tolist()
                    )
                checked["teacher_reads"] += 1
                checked["coarse_mismatch"] += left != right
                checked["fine_mismatch"] += left != right or lhs != rhs
    dump(
        out / f"completion-eval-{case}.json",
        dict(
            case=case,
            labels=counts,
            feasible_known=len(prob),
            positive_prevalence=float(labels_known.mean()),
            average_precision=float(
                (precision * sorted_y).sum() / sorted_y.sum().clamp_min(1)
            ),
            brier=float((prob - labels_known).square().mean()),
            completions=error(1, y[:, 2] > 0),
            visits=error(2, y[:, 4] > 0),
            address_audit=checked,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    torch.set_num_threads(1)
    for c in a.cases:
        assess(a.root, a.out, c)
