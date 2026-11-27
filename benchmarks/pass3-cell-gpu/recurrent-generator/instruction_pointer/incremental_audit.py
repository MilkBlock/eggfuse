"""Offline forward-use, native sparse control and sampled operator timing."""

import json
import os
from collections import Counter

import torch
from torch.utils._python_dispatch import TorchDispatchMode

from cell_kv_runtime import native
from continuous_stream import Stream
from continuous_trials import instrument, setup
from incremental_fit import corpus, output
from incremental_kv import InferenceCache
from joint_cell_sweep import complete_ce
from joint_cell_train import fitted
from partner_index_worlds import args
from prefix_train import make
from variable_binding_execution import SparsePolicy


def audit(a, case):
    out = output(a)
    n = fitted(a, case, "sweep", 0)
    n.grouped_training_reduction = True
    data, _, manifest = corpus(a, case, n)
    seen = set()
    hooks = []
    for name, mod in n.named_modules():
        params = tuple(f"{name}.{k}" for k, _ in mod.named_parameters(recurse=False))
        if params:
            hooks.append(
                mod.register_forward_pre_hook(
                    lambda mod, args, ps=params: seen.update(ps)
                )
            )
    # Direct Parameter reads (e.g. indexing lane embeddings) bypass Module.forward.
    names = {id(p): k for k, p in n.named_parameters()}

    class ParameterReads(TorchDispatchMode):
        def __torch_dispatch__(self, func, types, args=(), kwargs=None):
            for x in args:
                if id(x) in names:
                    seen.add(names[id(x)])
            return func(*args, **(kwargs or {}))

    counts = Counter()
    for w, s, targets in data:
        n.prepare(w)
        with ParameterReads():
            complete_ce(n, w, n.state(w, s), targets)
        for tid, refs in targets:
            counts["higher" if tid >= w.primitives else "primitive"] += 1
            counts[f"parents_{len(refs)}"] += 1
    for h in hooks:
        h.remove()
    params = {k: p.numel() for k, p in n.named_parameters() if k in seen}
    (out / f"forward-{case}.json").write_text(
        json.dumps({"signature": manifest, "forward": params, "targets": counts})
    )

    for cap in (64, 256):
        for seed in (193, 307):
            path = out / f"sparse-{case}-{cap}-{seed}.json"
            if path.exists():
                continue
            n, w, align = setup(a, case)
            n = make(a, "base").eval()
            pol = SparsePolicy(n, None, a, a.data / case)
            r = native(
                a,
                w,
                policy=pol,
                seed=seed,
                slots=6,
                submit_pages=2,
                receipt_memory=True,
                rule_state=True,
                paid_limit=cap,
                reference=align,
            )
            path.write_text(json.dumps(dict(r, counts=pol.count, decode=pol.decode_s)))

    sample = []

    class Profile(Stream):
        def generate(self, w, s, rng, slots):
            if 32 <= len(s["request_receipts"]) and len(sample) < 3:
                with torch.profiler.profile(
                    activities=[torch.profiler.ProfilerActivity.CPU]
                ) as prof:
                    tokens = super().generate(w, s, rng, slots)
                sample.append(
                    {
                        "run": s["run"],
                        "ports": len(s["ports"]),
                        "receipts": len(s["request_receipts"]),
                        "ops": {
                            e.key: [e.count, e.self_cpu_time_total]
                            for e in prof.key_averages()
                        },
                    }
                )
                return tokens
            return super().generate(w, s, rng, slots)

    n, w, align = setup(a, case)
    instrument(n, "exact")
    InferenceCache(n)
    native(
        a,
        w,
        policy=Profile(n, "A", incremental=False),
        seed=193,
        slots=6,
        submit_pages=2,
        receipt_memory=True,
        rule_state=True,
        paid_limit=64,
        reference=align,
    )
    (out / f"operators-{case}.json").write_text(json.dumps(sample))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        audit(args(), os.environ["TR_CASE"])
