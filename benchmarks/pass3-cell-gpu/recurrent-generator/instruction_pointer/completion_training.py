"""Offline exhaustive suffix certification in bounded typed domains. Unknowns stay censored."""

import argparse, itertools, json, math, random, subprocess
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import torch
from torch import nn
from torch.nn import functional as F
from recursive_train import folder, read, binary
from recursive_agent import Reader, Compose
from stream_guard import GuardStream, Study
from train_generation_targets import TRAIN
from protocol_experiment import dump


class Completion(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(nn.Linear(65, 32), nn.Tanh(), nn.Linear(32, 3))

    def forward(self, x):
        return self.layers(x)

    @staticmethod
    def features(s, depth, p, z):
        fanout = min(16, math.log1p(len(s.roles[depth + 1])))
        return torch.cat(
            (
                s.local(depth, p),
                s.rd.meta(s.rule).expand(len(z), -1),
                z,
                z.new_full((len(z), 1), fanout),
            ),
            1,
        )


def expand_cost(s, pre):
    paths = torch.tensor([pre])
    cost = 0
    for j in range(len(pre), len(s.roles)):
        children = []
        for parent, col in s.children(paths, j, 128):
            ps = torch.cat((paths[parent], col[:, None]), 1)
            if s.semi and j == len(s.roles) - 1:
                ps = ps[
                    torch.stack([s.tables[k][0][ps[:, k]] for k in range(j + 1)]).any(0)
                ]
            cost += len(ps)
            children.append(ps)
        if not children:
            break
        paths = torch.cat(children)
        if not len(paths):
            break
    return cost


@torch.no_grad()
def labels(root, case, seed):
    d = folder(root, case)
    rd = Reader(read(d / "program.json"), root, rename_seed=seed)
    base = Compose().eval()
    base.load_state_dict(
        torch.load(root / "recursive-agent/multi.pt", weights_only=True)
    )
    tape = read(d / "tape.json")
    by = defaultdict(lambda: defaultdict(list))
    for q in tape["requests"]:
        if len(q["parents"]) > 1:
            by[q["run"]][q["rule"]].append(q)
    rng = random.Random(seed)
    # Sample training Runs before looking at any held-out programs.
    available = sorted(by)
    selected = set(rng.sample(available, min(100, len(available))))
    samples = []
    queries = []
    batches = []
    for f in map(json.loads, (d / "memory.jsonl").open()):
        rd.advance(f)
        if f["run"] not in selected:
            continue
        for rid, qs in by[f["run"]].items():
            s = GuardStream(
                rd,
                base,
                rid,
                dict(f["rules"])[rid],
                Counter(),
                study=Study(bits=8, symmetric=True, delta_buckets=True),
            )
            s.prepare()
            idx = [{a: i for i, a in enumerate(ports)} for ports in s.roles]
            gold = {}
            for q in qs:
                pp = [q["parents"][j]["address"] for j in s.order]
                path = tuple(
                    idx[j][rd.store.alias(a["token"]), a["op"]]
                    for j, a in enumerate(pp)
                )
                gold[path] = q["token"]
            for width in range(1, len(s.roles)):
                roots = sorted({p[:width] for p in gold})
                seeds = rng.sample(roots, min(8, len(roots)))
                random_roots = [
                    tuple(rng.randrange(len(s.roles[j])) for j in range(width))
                    for _ in range(12)
                ]
                prefixes = list(dict.fromkeys(seeds + random_roots))
                pp = torch.tensor(prefixes)
                h = base.start(rd.meta(rid)).expand(len(pp), -1)
                for j in range(width):
                    _, h = s.logits(h, j, pp[:, : j + 1])
                xs = Completion.features(s, width - 1, pp, h)
                size = math.prod(map(len, s.roles[width:]))
                for x, pre in zip(xs, prefixes):
                    pos = {owner for p, owner in gold.items() if p[:width] == pre}
                    complete = size <= 72 and len(queries) + size <= 65000
                    start = len(queries)
                    cost = None
                    if complete:
                        cost = expand_cost(s, pre)
                        for suf in itertools.product(
                            *(range(len(ports)) for ports in s.roles[width:])
                        ):
                            parents = [None] * len(s.roles)
                            for k, i in enumerate(pre + suf):
                                t, op, v = s.port_refs(k)[i].tolist()
                                parents[s.order[k]] = dict(
                                    address=dict(token=t, op=op), version=v
                                )
                            queries.append(
                                dict(
                                    run=f["run"],
                                    rule=rid,
                                    token=len(queries) + 1,
                                    parents=parents,
                                )
                            )
                    samples.append(x)
                    batches.append((complete, start, len(queries), pos, cost))
    with TemporaryDirectory() as tmp:
        p = Path(tmp) / "probes.json"
        dump(p, {**tape, "requests": queries})
        audit = json.loads(
            subprocess.check_output(
                [
                    binary(root),
                    "replay",
                    d / "program.json",
                    d / "tape.json",
                    "time",
                    "--recall",
                    p,
                ]
            )
        )
    answers = {i: (owner, reason) for _, i, owner, reason in audit["recall_verdicts"]}
    assert len(answers) == len(queries)
    y = []
    counts = Counter()
    for complete, start, end, pos, cost in batches:
        additional_witness = False
        for i in range(start + 1, end + 1):
            owner, why = answers[i]
            if owner is not None:
                pos.add(owner)
            elif why == "off_reference":
                complete = False
                additional_witness = (
                    True  # valid but no canonical winner to deduplicate
                )
        n = max(len(pos), int(additional_witness))
        counts["unowned_witness_prefixes"] += additional_witness
        status = 1 if n else 0 if complete else -1
        counts[{1: "feasible", 0: "dead", -1: "unknown"}[status]] += 1
        y.append(
            [status, math.log1p(n), complete, math.log1p(cost or 0), cost is not None]
        )
    return torch.stack(samples), torch.tensor(y), dict(counts, probes=len(queries))


def fit(root, out):
    parts = [labels(root, c, 7159 + i) for i, c in enumerate(TRAIN)]
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    torch.manual_seed(31037)
    x = torch.cat([p[0] for p in parts]).to(dev)
    y = torch.cat([p[1] for p in parts]).to(dev)
    net = Completion().to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=0.003)
    for _ in range(650):
        ix = torch.randint(len(x), (160,), device=dev)
        pred = net(x[ix])
        b = y[ix]
        known = b[:, 0] >= 0
        loss = (
            F.binary_cross_entropy_with_logits(
                pred[:, 0], b[:, 0].clamp_min(0), reduction="none"
            )
            * known
        ).sum() / known.sum().clamp_min(1)
        delta = pred[:, 1] - b[:, 1]
        # Censored positive counts give a lower bound, never a zero negative.
        loss += (torch.where(b[:, 2] > 0, delta, delta.clamp_max(0)) ** 2).mean()
        loss += ((pred[:, 2] - b[:, 3]).square() * b[:, 4]).sum() / b[
            :, 4
        ].sum().clamp_min(1)
        opt.zero_grad()
        loss.backward()
        opt.step()
    torch.save(net.cpu().state_dict(), out / "continuation.pt")
    dump(
        out / "continuation-fit.json",
        dict(
            seed=31037,
            device=dev,
            steps=650,
            programs=dict(zip(TRAIN, (p[2] for p in parts))),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    fit(a.root, a.out)
