"""Width, native-state count, and exposure scaling under complete-token CE."""

import json
import os
import random
from collections import Counter
from time import perf_counter

import torch
from torch import nn
from torch.nn import functional as F

from abstraction_catalogue import score
from cell_kv_runtime import native
from constructible_study import TracePolicy, directory
from feedback_train import get
from foundation_world import data, folder
from partner_index_worlds import args

STEPS = (0, 32, 128, 512)


class WideRead(nn.Module):
    """Widen the existing GRU gates while retaining the 32-lane KV interface."""

    def __init__(self, base, width, jitter=0.007):
        super().__init__()
        self.copies = width // base.hidden_size
        if self.copies < 1 or width % base.hidden_size:
            raise ValueError("width must be a multiple of the KV interface")
        for name, p in base.named_parameters():
            tiled = p.detach().reshape(3, base.hidden_size, *p.shape[1:]).unsqueeze(1)
            tiled = (
                tiled.expand(-1, self.copies, -1, *p.shape[1:])
                .reshape(-1, *p.shape[1:])
                .clone()
            )
            noise = torch.randn_like(tiled) * jitter if p.ndim == 2 else 0.0
            setattr(self, name, nn.Parameter(tiled + noise))

    def forward(self, x, h):
        i = F.linear(x, self.weight_ih, self.bias_ih).chunk(3, -1)
        j = F.linear(h, self.weight_hh, self.bias_hh).chunk(3, -1)
        r = (i[0] + j[0]).sigmoid()
        z = (i[1] + j[1]).sigmoid()
        new = (i[2] + r * j[2]).tanh()
        expanded = (
            h.unsqueeze(-2).expand(*h.shape[:-1], self.copies, h.size(-1)).flatten(-2)
        )
        return (
            (new + z * (expanded - new))
            .reshape(*h.shape[:-1], self.copies, h.size(-1))
            .mean(-2)
        )


def model(a, seed, width, random_read=False):
    torch.manual_seed(seed)
    n = get(a, "visible", seed)
    n.load_state_dict(
        torch.load(directory(a) / f"structured-{seed}.pt", weights_only=True)
    )
    n.condition_on_types = True
    if width != 32:
        n.actor.next_read = WideRead(n.actor.next_read, width)
    if random_read:
        # Same per-gate input scale for all widths; train the recurrent read from scratch.
        torch.manual_seed(seed + 819)
        with torch.no_grad():
            for p in n.actor.next_read.parameters():
                p.uniform_(-(32**-0.5), 32**-0.5)
    return n


def train(a, cat, nprog, width, seed, ds, test, random_read=False, checkpoints=STEPS):
    out = folder(a)
    label = f"{cat}-{nprog}-{width}-{seed}"
    if checkpoints != STEPS:
        label = "long-" + label
    if random_read:
        label = "fresh-" + label
    path = out / f"curve-{label}.json"
    if path.exists() and (out / f"model-{label}.pt").exists():
        return
    net = model(a, seed, width, random_read)
    trainable = [p for p in net.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(trainable, lr=0.001, weight_decay=0)
    rng = random.Random(seed + 652)
    counts = Counter()
    seconds = 0.0
    curve = []
    available = sum(len(ss) for _, ss in ds)
    # Evaluate a fixed balanced train probe at all checkpoints (loss diagnostic).
    train_probe = ds[:4]
    for step in range(checkpoints[-1] + 1):
        if step in checkpoints:
            net.eval()
            net.physical = ("held", 0)
            with torch.no_grad():
                held = score(net, test)
                fit = score(net, train_probe)
                executions = []
                for i, (w, _) in enumerate(test):
                    for draw in (193, 827):
                        net.static_cache.clear()
                        pol = TracePolicy(net, True)
                        z = native(
                            a,
                            w,
                            policy=pol,
                            slots=12,
                            submit_pages=2,
                            receipt_memory=True,
                            seed=draw,
                            receipt_log=pol,
                        )
                        executions.append(
                            dict(
                                i=i,
                                arity=len(w.roles[w.root]),
                                draw=draw,
                                decisions=pol.count["signed"],
                                slots=pol.count["offered"],
                                decode=pol.decode_s,
                                **z,
                            )
                        )
            curve.append(
                {
                    "step": step,
                    "samples": 16 * step,
                    "touched": len(counts),
                    "states": available,
                    "trainable": sum(p.numel() for p in trainable),
                    "total": sum(p.numel() for p in net.parameters()),
                    "seconds": seconds,
                    "fit": fit,
                    "held": held,
                    "runs": executions,
                }
            )
        if step == checkpoints[-1]:
            break
        start = perf_counter()
        net.train()
        terms = []
        for _ in range(4):
            # Common curriculum phases across all budgets and dataset sizes.
            easy = rng.random() < (0.75 if step < 32 else 0.50 if step < 128 else 0.25)
            pool = [i for i in range(nprog) if (i % 4 < 2) == easy]
            i = rng.choice(pool)
            w, ss = ds[i]
            j = rng.randrange(len(ss))
            s, valid = ss[j]
            counts[i, j] += 1
            net.prepare(w)
            m = net.state(w, s)
            picks = rng.choices(valid, k=4)
            losses = {t: net.token_loss(w, m, t) for t in set(picks)}
            terms.extend(losses[t] for t in picks)
        opt.zero_grad(set_to_none=True)
        loss = torch.stack(terms).mean()
        if not torch.isfinite(loss):
            raise ValueError("positive target outside the decoder support")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(trainable, 3)
        opt.step()
        seconds += perf_counter() - start
    path.write_text(json.dumps(curve, separators=(",", ":")))
    torch.save(net.state_dict(), out / f"model-{label}.pt")
    print(label, held, seconds, flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    actor = model(a, 71, 32).actor
    for cat in os.getenv("FC_CATS", "multi primitive short medium half").split():
        full = cat == "multi"
        test = data(a, actor, cat, False, 4)
        ds = data(a, actor, cat, True, 24 if full else 12)
        for width in (32, 128, 512) if full else (32,):
            for size in (4, 12, 24) if full else (12,):
                for seed in (71, 113):
                    train(a, cat, size, width, seed, ds[:size], test)
