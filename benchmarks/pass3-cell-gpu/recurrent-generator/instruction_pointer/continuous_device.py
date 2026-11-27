"""Offline timing of resident base-address logits from one actual model decision view."""

import json
import math
import os
import statistics
from time import perf_counter

import numpy as np
import torch

from competition_draw import Page
from continuous_stream import Stream
from continuous_trials import output, run_native, setup
from partner_index_worlds import args


def score(q, k, bias, role, tables):
    logits = q @ k.T / math.sqrt(k.shape[-1]) - bias
    return logits.masked_fill(role[:, None] != tables, -torch.inf).softmax(1)


def measure(n, w, s):
    page = Page(n, w, s)
    m = page.m
    rows = []
    # Record only queries actually reached by a learned sampler. No paired-parent grid.
    original = n.address

    def capture(world, mem, tid, prefix):
        lp = original(world, mem, tid, prefix)
        if lp is not None:
            nodes, codes, _ = n.cache
            rid = w.layouts[tid][0][0]
            h = (mem["ctx"] + codes[tid]).tanh()
            for idx in prefix:
                h = n.actor.next_read(mem["ext"][idx], h)
            q = n.actor.query(h + nodes[w.cat.inputs["generated", rid][len(prefix)]])
            rows.append((q, w.roles[rid][len(prefix)]))
        return lp

    n.address = capture
    try:
        page.draws(np.random.default_rng(71), 128, True)
    finally:
        n.address = original
    if not rows:
        return None
    keys = (m["keys"][m["group"]] + m["ek"]).contiguous()
    bias = torch.bincount(m["group"]).float().log()[m["group"]]
    queries = torch.stack([q for q, _ in rows])
    roles = torch.tensor([role for _, role in rows])
    results = []
    for batch in (1, 4, 16, 64):
        if batch > len(rows):
            continue
        ref = None
        for device in ("cpu", "mps"):
            if device == "mps" and not torch.backends.mps.is_available():
                continue
            fence = torch.mps.synchronize if device == "mps" else lambda: None
            start = perf_counter()
            k, b, t, q, role = [
                v.to(device)
                for v in (keys, bias, m["tables"], queries[:batch], roles[:batch])
            ]
            fence()
            setup_time = perf_counter() - start

            value = score(q, k, b, role, t).cpu()
            if ref is None:
                ref = value
            err = float((value - ref).abs().max())
            assert err < 2e-5
            timings = []
            for _ in range(5):
                fence()
                tick = perf_counter()
                for _ in range(32):
                    score(q, k, b, role, t)
                fence()
                timings.append((perf_counter() - tick) / 32)
            results.append(
                {
                    "batch": batch,
                    "rows": len(keys),
                    "device": device,
                    "setup": setup_time,
                    "max_probability_error": err,
                    "median_seconds": statistics.median(timings),
                    "timings": timings,
                    "upload_bytes": sum(x.nbytes for x in (k, b, t, q, role))
                    if device == "mps"
                    else 0,
                }
            )
    return results


class Probe(Stream):
    results = None

    def generate(self, w, s, rng, slots):
        if (
            self.results is None
            and len(s["ports"]) >= 128
            and len(s["request_receipts"]) >= 32
            and s["menu"]
        ):
            self.results = measure(self.net, w, s)
        return super().generate(w, s, rng, slots)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    case = os.environ["TR_CASE"]
    with torch.no_grad():
        n, w, align = setup(a, case)
        pol = Probe(n, "A")
        run_native(a, w, align, pol, 193, 256)
        assert pol.results
        (output(a) / f"device-{case}.json").write_text(json.dumps(pol.results))
