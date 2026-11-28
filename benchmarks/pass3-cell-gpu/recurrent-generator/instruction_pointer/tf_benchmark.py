"""Matched native-corpus teacher-forcing microbenchmark; no Runtime in timed updates."""

import ctypes
import json
import os
import resource
import threading
from time import perf_counter
import torch
from joint_cell_sweep import complete_ce
from partner_index_worlds import args
from scaling_fit import model
from scaling_pool import Pool, Sampler
from teacher_forcing import complete_nll


def run(a):
    torch.set_num_threads(1)
    cfg = {"arm": os.getenv("TF_ARM", "A")}
    n, _ = model(a, cfg, 71)
    p = Pool(a, n)
    sampler = Sampler(p, 71, {})
    rows = [sampler.next(0.5) for _ in range(16)]
    counter = None
    if os.getenv("TF_METAL_COUNTER"):
        counter = ctypes.CDLL(os.environ["TF_METAL_COUNTER"])
        if not counter.install_dispatch_counter():
            raise RuntimeError("Metal command encoder unavailable")
        counter.count_dispatches.restype = ctypes.c_ulong
    reference = {}
    for mode, device in [
        ("A", "cpu"),
        ("B", "cpu"),
        ("C", "cpu"),
        ("B", "mps"),
        ("C", "mps"),
    ]:
        if os.getenv("TF_ONLY") and mode + ":" + device != os.environ["TF_ONLY"]:
            continue
        if device == "mps" and not torch.backends.mps.is_available():
            continue
        n, opt = model(a, cfg, 71)
        seconds = [0.0] * 3
        errors = [0.0] * 3
        peak = 0
        sync_seconds = 0.0
        initial_dispatches = counter.count_dispatches() if counter else None
        observe = device == "mps" and os.getenv("TF_SAMPLE_DEVICE") == "1"
        samples = []
        done = threading.Event()

        def sample_device():
            while not done.wait(0.001):
                samples.append(torch.mps.driver_allocated_memory())

        if observe:
            observer = threading.Thread(target=sample_device, daemon=True)
            observer.start()
        for i in range(0, len(rows), 4):
            batch = [(w, s, t) for _, w, s, t in rows[i : i + 4]]
            opt.zero_grad(set_to_none=True)
            start = perf_counter()
            if mode == "A":
                chunks = []
                for w, s, t in batch:
                    n.prepare(w)
                    n.physical = ("held", 0)
                    chunks.append(complete_ce(n, w, n.state(w, s), t) * len(t))
                loss = torch.stack(chunks).sum() / sum(len(t) for w, s, t in batch)
            else:
                chunks = (
                    [complete_nll(n, [x], device) for x in batch]
                    if mode == "B"
                    else [complete_nll(n, batch, device)]
                )
                loss = torch.cat(chunks).mean()
            if device == "mps":
                fence_start = perf_counter()
                torch.mps.synchronize()
                sync_seconds += perf_counter() - fence_start
            middle = perf_counter()
            loss.backward()
            if device == "mps":
                fence_start = perf_counter()
                torch.mps.synchronize()
                sync_seconds += perf_counter() - fence_start
            end = perf_counter()
            opt.step()
            seconds = [
                a + b
                for a, b in zip(
                    seconds, (middle - start, end - middle, perf_counter() - end)
                )
            ]
            g = torch.cat(
                [x.grad.flatten() for x in n.parameters() if x.grad is not None]
            )
            weights = torch.cat([x.detach().flatten() for x in n.parameters()])
            got = (loss.item(), g.clone(), weights)
            if mode == "A":
                reference[i] = got
            elif i in reference:
                orig = reference[i]
                errors = [
                    max(errors[0], abs(got[0] - orig[0])),
                    max(errors[1], (g - orig[1]).abs().max().item()),
                    max(errors[2], (weights - orig[2]).abs().max().item()),
                ]
            if device == "mps":
                peak = max(peak, torch.mps.driver_allocated_memory())
        if observe:
            done.set()
            observer.join()
        tokens = sum(len(x[3]) for x in rows)
        print(
            json.dumps(
                dict(
                    mode=mode,
                    device=device,
                    tokens=tokens,
                    unique=len({(k, t) for k, w, s, ts in rows for t in ts}),
                    updates=4,
                    seconds=seconds,
                    tokens_per_s=tokens / sum(seconds),
                    errors=errors if mode == "A" or reference else None,
                    explicit_sync_seconds=sync_seconds,
                    direct_metal_kernel_dispatches=counter.count_dispatches()
                    - initial_dispatches
                    if counter
                    else None,
                    process_highwater_bytes=resource.getrusage(
                        resource.RUSAGE_SELF
                    ).ru_maxrss,
                    driver_bytes_after_step=peak,
                    driver_bytes_sampled_peak=max(samples) if samples else None,
                    memory_samples=len(samples),
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    run(args())
