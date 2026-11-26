"""Controlled capacity and native rollout measurements for the existing response-conditioned D4."""

import argparse
import hashlib
import math
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from discrete_cells import Marks
from discrete_editor import Rates, features
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from response_plan import ResponsePolicy
from response_study import memory, training_examples
from scaling_bake import save
from transaction_native import execute

SIZES = {
    "base": 0,
    "100K": 100_000,
    "1M": 1_000_000,
    "10M": 10_000_000,
    "50M": 50_000_000,
}
CASES = ("fact", "loopfact", "sum-divisors", "grammar-benefit-left-17119")


def models(size):
    marks, rates = Marks(), Rates()
    if size == "base":
        return marks, rates
    # Keep the mark/rate capacity split close to the existing model. FP32 throughout.
    for base, key, portion, activation in (
        (marks, "choice", 0.31, nn.Tanh),
        (rates, "net", 0.69, nn.SiLU),
    ):
        original = getattr(base, key)
        inputs, outputs = original[0].in_features, original[-1].out_features
        layers = 2 if size in ("100K", "1M") else 3
        b = inputs + outputs + layers
        width = max(
            8,
            8
            * round(
                (
                    math.sqrt(
                        b * b + 4 * (layers - 1) * (SIZES[size] * portion - outputs)
                    )
                    - b
                )
                / (2 * (layers - 1) * 8)
            ),
        )
        modules = [nn.Linear(inputs, width), activation()]
        for _ in range(layers - 1):
            modules.extend((nn.Linear(width, width), activation()))
        modules.append(nn.Linear(width, outputs))
        setattr(base, key, nn.Sequential(*modules))
    return marks, rates


def tensors(recs, labels, seed, draws):
    rng = np.random.default_rng(seed)
    xx, yy = [], []
    for z, e, src, dst, vec, path in recs:
        for _ in range(draws):
            n = len(path)
            k = rng.integers(n + 1)
            t = float(rng.beta(k + 1, n - k + 1))
            current = path[k][0] if k < n else dst
            target = torch.zeros(len(current) + 1, 3)
            if k < n:
                _, idx, kind, _ = path[k]
                target[idx, kind] = n - k
            xx.append(features(z, e, [vec[v.cell] for v in current], t))
            yy.append(target)
    return {
        "rate": (torch.cat(xx), torch.cat(yy)),
        "mark": (
            torch.stack([x for x, _, _ in labels]),
            torch.tensor([y for _, y, _ in labels]).float(),
            torch.tensor([w for _, _, w in labels]).float(),
        ),
    }


def prepare(a):
    from latent_cell_flow import TRAIN

    for label, sources, limit in (
        ("small", TRAIN, 12),
        ("large", TRAIN, 256),
        ("held", ("dot",), 64),
    ):
        rec, marks, kinds, _ = training_examples(a, sources, limit)
        train = tensors(rec, marks, 835, 8)
        # Fixed independent bridge draws for fitting and generalization scores.
        test = tensors(rec, marks, 391, 4)
        torch.save((train, test), a.out / (label + ".pt"))
        save(
            a.out / (label + ".json"),
            {
                "sources": sources,
                "windows_limit": limit,
                "plans": len(rec),
                "branch_decisions": len(marks),
                "kinds": kinds,
                "rate_sites": len(train["rate"][0]),
            },
        )
        print(label, len(rec), len(marks), flush=True)


def objective(net, data, kind):
    x, y, *rest = data
    raw = net(x)
    if kind == "mark":
        logits = raw.flatten()
        loss = (
            rest[0] * F.binary_cross_entropy_with_logits(logits, y, reduction="none")
        ).mean()
        return loss, (logits.ge(0) == y.bool()).float().mean()
    mu = F.softplus(raw)
    allowed = torch.ones_like(mu)
    allowed[:, 1:] = x[:, -5, None]
    loss = ((mu - y * mu.clamp_min(1e-8).log()) * allowed).sum(1).mean()
    # Positive next-jump sites only; do not reward correctly predicting no jump.
    return loss, (raw.argmax(1) == y.argmax(1)).float()[y.sum(1) > 0].mean()


@torch.no_grad()
def assess(net, data, kind):
    weighted = accuracy = 0.0
    n = positive = 0
    for i in range(0, len(data[0]), 512):
        subset = [v[i : i + 512].to("mps") for v in data]
        loss, acc = objective(net, subset, kind)
        count = len(subset[0])
        k = count if kind == "mark" else int((subset[1].sum(1) > 0).sum().item())
        weighted += loss.item() * count
        if k:
            accuracy += acc.item() * k
        n += count
        positive += k
    return {
        "loss": weighted / n,
        "accuracy": accuracy / max(1, positive),
        "rows": n,
        "accuracy_denominator": positive,
    }


def fit(a, size, dataset):
    torch.manual_seed(243)
    pair = models(size)
    train, test = torch.load(a.out / (dataset + ".pt"), weights_only=True)
    _, held = torch.load(a.out / "held.pt", weights_only=True)
    report = {}
    directory = a.out / (size + "-" + dataset)
    directory.mkdir(exist_ok=True)
    for net, kind in ((pair[0].choice, "mark"), (pair[1], "rate")):
        net.to("mps")
        data = [v.to("mps") for v in train[kind]]
        opt = torch.optim.AdamW(net.parameters(), lr=a.lr)
        rng = torch.Generator().manual_seed(683)
        curve = []
        t = perf_counter()
        for step in range(1, a.updates + 1):
            ids = torch.randint(len(data[0]), (a.batch,), generator=rng).to("mps")
            opt.zero_grad(set_to_none=True)
            loss, _ = objective(net, [v[ids] for v in data], kind)
            loss.backward()
            opt.step()
            if step in (a.updates // 4, a.updates // 2, a.updates):
                curve.append(
                    {
                        "step": step,
                        "train": assess(net, test[kind], kind),
                        "held": assess(net, held[kind], kind),
                    }
                )
        torch.mps.synchronize()
        report[kind] = {
            "parameters": sum(v.numel() for v in net.parameters()),
            "curve": curve,
            "seconds": perf_counter() - t,
        }
        del opt, data
        net.cpu()
    pt = directory / "weights.pt"
    torch.save([v.state_dict() for v in pair], pt)
    with pt.open("rb") as f:
        report["sha256"] = hashlib.file_digest(f, "sha256").hexdigest()
    save(
        directory / "fit.json",
        dict(
            size=size, data=dataset, batch=a.batch, lr=a.lr, updates=a.updates, **report
        ),
    )
    print(
        size,
        dataset,
        [round(report[k]["curve"][-1]["held"]["loss"], 4) for k in ("mark", "rate")],
        flush=True,
    )


class Inference(nn.Module):
    """Keep parameters resident; return the actual result to the existing host-side consumer."""

    def __init__(self, net, device, counts, label):
        super().__init__()
        self.core = net.to(device)
        self.device = device
        self.counts = counts
        self.label = label

    def forward(self, *inputs):
        t = perf_counter()
        result = self.core(*(v.to(self.device) for v in inputs)).to("cpu")
        self.counts[self.label + "_seconds"] += perf_counter() - t
        self.counts[self.label + "_calls"] += 1
        self.counts[self.label + "_input_bytes"] += sum(
            v.numel() * v.element_size() for v in inputs
        )
        self.counts[self.label + "_output_bytes"] += (
            result.numel() * result.element_size()
        )
        return result


@torch.inference_mode()
def execute_one(a, size, dataset, device, case, block):
    prefix = a.out / (size + "-" + dataset)
    d = folder(a.data, case)
    counts = Counter()
    with TemporaryDirectory(dir=a.out) as tmp:
        target = Target(
            read(d / "program.json"),
            snapshot(a.data, d, "reference", "-", None, Path(tmp) / "ref.json")[0],
        )
        initial = target.match(
            snapshot(a.data, d, "reference", "-", 0, Path(tmp) / "ref.json")[0]
        )
        t = perf_counter()
        m = memory(a, d, encoder_device=device if a.device_gnn else "cpu")
        marks, rates = models(size)
        weights = torch.load(
            prefix / "weights.pt", weights_only=True, map_location="cpu"
        )
        for net, sd in zip((marks, rates), weights, strict=True):
            net.load_state_dict(sd)
        del weights
        marks.choice = Inference(marks.choice, device, counts, "mark")
        rates = Inference(rates, device, counts, "rate")
        for key in ("dynamic", "age", "next_read"):
            original = getattr(m.enc.actor, key)
            setattr(m.enc.actor, key, Inference(original, device, counts, key))
        pol = ResponsePolicy(m, marks, {"flow": rates}, "empty", 4, 536, 2)
        setup = perf_counter() - t
        r = execute(a.data, case, study=pol, seconds=a.seconds, series=tmp)
        if r["termination"] != "schedule_end":
            raise RuntimeError((case, size, r["termination"]))
        graph = read(Path(tmp) / (case + "-stream-multi") / "state.json")
        facts = sorted(target.match(graph) - initial)
        wall = r["wall"] + setup + r["runtime_setup_seconds"]
        r.pop("trace", None)
        r.update(
            size=size,
            dataset=dataset,
            device=device,
            block=block,
            covered=len(facts),
            facts=facts,
            reference=len(target.gold) - len(initial),
            setup=setup,
            cold_wall=wall,
            cold_eps=r["signed_ops"] / wall,
            inference=dict(counts),
        )
        save(prefix / f"{a.timing_prefix}{case}-{device}-b{block}.json", r)
        print(
            case, size, dataset, device, block, len(facts), round(wall, 3), flush=True
        )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["prepare", "fit", "run"])
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--data", type=Path, default=Path("/tmp/dfm-local/data"))
    p.add_argument(
        "--actor", type=Path, default=Path("run-recall/higher-scaling/weights/actor.pt")
    )
    p.add_argument(
        "--forks",
        type=Path,
        default=Path("/Volumes/Extreme SSD/eggfuse-experiments/latent-flow-1125"),
    )
    p.add_argument("--rollout", type=Path, default=Path("/tmp/dfm-local/rollout"))
    p.add_argument(
        "--device-gnn",
        action="store_true",
        help="Also encode the frozen Recipe and Higher graphs on the inference device.",
    )
    p.add_argument("--timing-prefix", default="")
    p.add_argument("--seconds", type=int, default=300)
    p.add_argument("--updates", type=int, default=192)
    p.add_argument("--batch", type=int, default=128)
    p.add_argument("--lr", type=float, default=0.0005)
    p.add_argument("--sizes", nargs="+", choices=list(SIZES), default=list(SIZES))
    p.add_argument(
        "--datasets", nargs="+", choices=["small", "large"], default=["small", "large"]
    )
    p.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    p.add_argument("--devices", nargs="+", choices=["cpu", "mps"], default=["mps"])
    p.add_argument("--blocks", type=int, default=2)
    a = p.parse_args()
    a.out.mkdir(exist_ok=True, parents=True)
    a.macro = False
    torch.set_num_threads(1)
    if not torch.backends.mps.is_available():
        raise RuntimeError("MPS unavailable")
    if a.action == "prepare":
        prepare(a)
    elif a.action == "fit":
        for size in a.sizes:
            for dataset in a.datasets:
                fit(a, size, dataset)
    else:
        jobs = [
            (size, ds, dev, case)
            for case in a.cases
            for size in a.sizes
            for ds in a.datasets
            for dev in a.devices
        ]
        for b in range(a.blocks):
            for size, ds, dev, case in jobs if b % 2 == 0 else reversed(jobs):
                execute_one(a, size, ds, dev, case, b)


if __name__ == "__main__":
    main()
