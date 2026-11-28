"""Exclusive host timers for the scalar teacher-forced reference on the same 16 native states."""

import json
from collections import Counter
from contextlib import contextmanager
from time import perf_counter
import torch
from partner_index_worlds import args
from scaling_fit import model
from scaling_pool import Pool, Sampler
from joint_cell_sweep import complete_ce


def run(a):
    torch.set_num_threads(1)
    n, opt = model(a, {"arm": "A"}, 71)
    p = Pool(a, n)
    sampler = Sampler(p, 71, {})
    rows = [sampler.next(0.5) for _ in range(16)]
    seconds, calls = Counter(), Counter()
    stack = []

    @contextmanager
    def section(name):
        start = perf_counter()
        stack.append(name)
        try:
            yield
        finally:
            delta = perf_counter() - start
            stack.pop()
            seconds[name] += delta
            calls[name] += 1
            if stack:
                seconds[stack[-1]] -= delta

    def wrap(obj, method, label):
        original = getattr(obj, method)

        def measured(*args, **kwargs):
            with section(label):
                return original(*args, **kwargs)

        setattr(obj, method, measured)

    wrap(n, "address", "candidate_scoring")
    wrap(n, "variant_prob", "template_variant")
    for k in ("query", "next_read"):
        wrap(getattr(n.actor, k), "forward", "query")
    for i in range(0, len(rows), 4):
        batch = rows[i : i + 4]
        opt.zero_grad(set_to_none=True)
        chunks = []
        for _, w, s, ts in batch:
            with section("graph_and_interface"):
                n.prepare(w)
            n.physical = ("held", 0)
            with section("memory_state"):
                m = n.state(w, s)
            with section("ce"):
                chunks.append(complete_ce(n, w, m, ts) * len(ts))
        with section("ce"):
            loss = torch.stack(chunks).sum() / sum(len(ts) for _, _, _, ts in batch)
        with section("backward"):
            loss.backward()
        with section("optimizer"):
            opt.step()
    print(
        json.dumps(
            dict(
                seconds=seconds,
                calls=calls,
                sync_device_seconds=0,
                device="cpu",
                states=len(rows),
                tokens=sum(len(ts) for _, _, _, ts in rows),
            )
        )
    )


if __name__ == "__main__":
    run(args())
