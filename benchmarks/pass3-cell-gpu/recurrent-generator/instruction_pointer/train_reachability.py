"""Learn continuation from a prefix and the next typed slot, before discarding a branch."""

import argparse, json, random
from collections import defaultdict, Counter
from pathlib import Path
import torch
from torch import nn
from torch.nn import functional as F
from generation_frontier import Generator
from recursive_agent import Reader, Compose
from recursive_train import folder, read
from train_generation_targets import TRAIN
from cell_stream import CellStream
from protocol_experiment import dump


class Prefix(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(36 + 4 + 24 + 48, 48), nn.Tanh(), nn.Linear(48, 1)
        )

    def forward(self, x):
        return self.net(x).flatten()

    @staticmethod
    def evidence(stream, depth, paths, z, look=True):
        if not hasattr(stream, "summaries"):
            stream.summaries = {}
        if not look:
            stream.summaries.setdefault(depth, z.new_zeros(48))
        if depth not in stream.summaries:
            bank = stream.tables[depth + 1][1]
            stream.summaries[depth] = torch.cat((bank.mean(0), bank.amax(0)))
            stream.stats["lookahead_port_reads"] += len(bank)
        return torch.cat(
            (
                stream.local(depth, paths),
                stream.rd.meta(stream.rule).expand(len(z), -1),
                z,
                stream.summaries[depth].expand(len(z), -1),
            ),
            1,
        )


@torch.no_grad()
def examples(root, case, seed):
    d = folder(root, case)
    prog = read(d / "program.json")
    rd = Reader(prog, root, rename_seed=seed)
    model = Compose().eval()
    model.load_state_dict(
        torch.load(root / "recursive-agent/multi.pt", weights_only=True)
    )
    by = defaultdict(lambda: defaultdict(list))
    for q in read(d / "tape.json")["requests"]:
        if len(q["parents"]) > 1:
            by[q["run"]][q["rule"]].append(q)
    rng = random.Random(seed)
    data = []
    lab = []
    with (d / "memory.jsonl").open() as frames:
        for f in map(json.loads, frames):
            rd.advance(f)
            for rule, group in by[f["run"]].items():
                s = CellStream(rd, model, rule, dict(f["rules"])[rule], Counter())
                s.prepare()
                idx = [{a: i for i, a in enumerate(ports)} for ports in s.roles]
                paths = set()
                for q in group:
                    pp = [q["parents"][j]["address"] for j in s.order]
                    paths.add(
                        tuple(
                            idx[j][rd.store.alias(a["token"]), a["op"]]
                            for j, a in enumerate(pp)
                        )
                    )
                for depth in range(len(s.order) - 1):
                    gold = sorted({path[: depth + 1] for path in paths})
                    seen = set(gold)
                    pos = rng.sample(gold, min(len(gold), 40))
                    candidates = list(pos)
                    for p in pos:
                        for j in range(len(p)):
                            for _ in range(3):
                                n = (
                                    *p[:j],
                                    rng.randrange(len(s.roles[j])),
                                    *p[j + 1 :],
                                )
                                if n not in seen:
                                    candidates.append(n)
                                    seen.add(n)
                    pp = torch.tensor(candidates)
                    h = model.start(rd.meta(rule)).expand(len(pp), -1)
                    for j in range(depth + 1):
                        _, h = s.logits(h, j, pp[:, : j + 1])
                    data.append(Prefix.evidence(s, depth, pp, h))
                    lab.extend([1] * len(pos) + [0] * (len(pp) - len(pos)))
    return torch.cat(data), torch.tensor(lab).float()


def fit(root, out):
    torch.manual_seed(32071)
    parts = [examples(root, c, 8749 + i) for i, c in enumerate(TRAIN)]
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    x, y = [torch.cat(v).to(dev) for v in zip(*parts)]
    net = Prefix().to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=0.002)
    pos = torch.where(y == 1)[0]
    neg = torch.where(y == 0)[0]
    for _ in range(420):
        ix = torch.cat(
            (
                pos[torch.randint(len(pos), (120,), device=dev)],
                neg[torch.randint(len(neg), (72,), device=dev)],
            )
        )
        loss = F.binary_cross_entropy_with_logits(net(x[ix]), y[ix])
        opt.zero_grad()
        loss.backward()
        opt.step()
    torch.save(net.cpu().state_dict(), out / "prefix.pt")
    dump(
        out / "prefix-fit.json",
        dict(
            seed=32071,
            device=dev,
            steps=420,
            programs={c: [len(y), int(y.sum())] for c, (_, y) in zip(TRAIN, parts)},
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    fit(a.root, a.out)
