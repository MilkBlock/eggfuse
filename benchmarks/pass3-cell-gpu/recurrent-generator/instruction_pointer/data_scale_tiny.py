"""Teacher-forced vs free binding and plan reproduction, with identical small native contexts."""

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from discrete_cells import from_q
from discrete_editor import features, sampler
from latent_cell_flow import Frozen
from metal_scaling import models, objective
from recursive_train import read
from response_plan import ResponseMemory
from response_study import memory


class Cases:
    def __init__(self, a):
        self.rows = []
        for i in range(4):
            d = a.out / "programs" / f"{i:04d}"
            m = memory(a, d)
            if i == 0:
                self.actor, self.scorer = m.enc.actor, self.load_scorer()
            tape = read(d / "teacher.json")["requests"]
            frames = list(
                map(json.loads, (d / "memory.jsonl").read_text().splitlines())
            )
            for f in (0, 1):
                good = [from_q(q) for q in tape if q["run"] == frames[f]["run"]]
                target = sorted(good, key=lambda c: -len(c.refs))[i + 2]
                self.rows.append(
                    (
                        read(d / "program.json"),
                        m.contract,
                        m.menu,
                        frames[: f + 1],
                        target,
                        set(good),
                    )
                )
        self.cached = []
        with torch.no_grad():
            for j in range(len(self.rows)):
                self.cached.append(self.view(j))

    def load_scorer(self):
        from latent_cell_flow import WIDTH
        from ripsat_policy import CellScorer

        net = CellScorer(WIDTH)
        net.load_state_dict(
            torch.load(
                "run-recall/parameterized-deep-ripsat/event-gnn.pt", weights_only=True
            )["model"]
        )
        return net

    def view(self, j):
        prog, ct, menu, frames, _, _ = self.rows[j]
        m = ResponseMemory(Frozen(prog, self.actor, self.scorer), ct, menu, self.scorer)
        for f in frames:
            m.update(f)
        return m


def measure(net, rate, cases):
    rng = np.random.default_rng(522)
    c = Counter()
    with torch.no_grad():
        for j, row in enumerate(cases.rows):
            m = cases.view(j)
            wanted, valid = row[-2:]
            labels = []
            net.draw(m, rng, Counter(), target=wanted, records=labels)
            for x, y, _ in labels:
                pred = net.choice(x).item() >= 0
                kind = "template" if x[-3] == 1 else "parent"
                c[kind + "_correct"] += int(pred == bool(y))
                c[kind + "_total"] += 1
            chosen = []
            for _ in range(64):
                m.on_template_draw = chosen.append
                draw = net.draw(m, rng, Counter())
                c["draws"] += 1
                c["free_exact_template"] += int(
                    chosen[-1] == (wanted.rule, wanted.higher)
                )
                del m.on_template_draw
                c["free_exact_binding"] += int(draw == wanted)
                c["free_legal_binding"] += int(draw in valid)
                seq = [
                    x.cell for x in sampler(rate, net, m, (), "flow", 4, rng, Counter())
                ]
                c["free_exact_plan"] += int(seq == [wanted])
                c["free_any_legal"] += int(any(x in valid for x in seq))
                c["issued"] += len(seq)
                c["legal_tokens"] += sum(x in valid for x in seq)
    return dict(c)


def run(a, arm, seed):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    cases = Cases(a)
    mark, rate = models("100K")
    if arm == "wide_mark":
        mark = models("1M")[0]
    if arm == "wide_rate":
        rate = models("1M")[1]
    encoder = arm in {"joint", "encoder"}
    for p in [*cases.actor.parameters(), *cases.scorer.parameters()]:
        p.requires_grad_(encoder)
    for p in [*mark.parameters(), *rate.parameters()]:
        p.requires_grad_(arm != "encoder")
    ps = [
        p
        for n in (mark, rate, cases.actor, cases.scorer)
        for p in n.parameters()
        if p.requires_grad
    ]
    opt = torch.optim.AdamW(ps, lr=0.001)
    curve = []
    for step in range(1, a.steps + 1):
        j = int(rng.integers(len(cases.rows)))
        m = cases.view(j) if encoder else cases.cached[j]
        target = cases.rows[j][-2]
        labels = []
        mark.draw(m, rng, Counter(), target=target, records=labels)
        x = torch.stack([x for x, _, _ in labels])
        y = torch.tensor([v for _, v, _ in labels]).float()
        markloss = F.binary_cross_entropy_with_logits(mark.choice(x).flatten(), y)
        rows = []
        labels = []
        vec = m.embed(target)
        for _ in range(8):
            done = rng.integers(2)
            t = rng.beta(done + 1, 2 - done)
            rows.append(features(m.state, m.event, [vec] if done else [], t))
            label = torch.zeros(1 + done, 3)
            if not done:
                label[0, 0] = 1
            labels.append(label)
        rateloss, _ = objective(rate, (torch.cat(rows), torch.cat(labels)), "rate")
        opt.zero_grad(set_to_none=True)
        (markloss + rateloss).backward()
        torch.nn.utils.clip_grad_norm_(ps, 5.0)
        opt.step()
        if step in (a.steps // 2, a.steps):
            curve.append(dict(step=step, **measure(mark, rate, cases)))
    dest = a.out / ("tiny" if a.steps == 768 else f"tiny-{a.steps}")
    dest.mkdir(exist_ok=True)
    (dest / f"{arm}-{seed}.json").write_text(json.dumps(curve) + "\n")
    torch.save(
        {
            "mark": mark.state_dict(),
            "rate": rate.state_dict(),
            "actor": cases.actor.state_dict(),
            "scorer": cases.scorer.state_dict(),
        },
        dest / f"{arm}-{seed}.pt",
    )
    print(arm, seed, curve[-1], flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--actor", type=Path, default=Path("run-recall/higher-scaling/weights/actor.pt")
    )
    p.add_argument("--data", type=Path, default=Path("/tmp/dfm-local/data"))
    p.add_argument("--steps", type=int, default=768)
    p.add_argument(
        "--arms",
        nargs="+",
        default=["frozen", "wide_mark", "wide_rate", "joint", "encoder"],
    )
    p.add_argument("--seeds", nargs="+", type=int, default=[243, 8201])
    a = p.parse_args()
    torch.set_num_threads(1)
    for name in a.arms:
        for seed in a.seeds:
            run(a, name, seed)
