"""Fit a local-yield ridge head on generated constructor contexts, then freeze it."""
from collections import Counter
import numpy as np


def features(program):
    ports, ops = program
    uses = Counter(index for _,_,args in ops for kind,index in args if kind=="result")
    return [1, len(ops), len(ports), sum(map(len,(a for _,_,a in ops))),
            len(set(name for name,_,_ in ops)), sum(max(0,n-1) for n in uses.values()),
            sum(s in {"i64","String","bool","f64"} for s in ports)]


def training_set(programs):
    # Independent local e-graphs with randomly shared boundary values,
    # pre-existing constructor keys, and retired intermediate results.
    rng = np.random.default_rng(1703)
    xs, ys = [], []
    for program in programs:
        ports, ops = program
        samples = []
        for _ in range(24):
            boundary = [(kind, int(rng.integers(4))) for kind in ports]
            table, results, visible_new = {}, [], set()
            for name,_,args in ops:
                key = (name, tuple((boundary if kind=="port" else results)[idx] for kind,idx in args))
                if key not in table:
                    value = ("constructor", len(table))
                    table[key] = value
                    if rng.random() >= 0.25:
                        visible_new.add(value)
                results.append(table[key])
            # Keep the root visible. Surviving intermediate identities are
            # sampled independently of the model, once per physical origin.
            samples.append(sum(v==results[-1] or rng.random()>=0.25 for v in sorted(visible_new)))
        xs.append(features(program))
        ys.append(np.mean(samples))
    return np.asarray(xs, dtype=np.float32), np.asarray(ys, dtype=np.float32)


def export_policy(library, checkpoint, largest=False):
    # Static features and eligible source sites only. Rust performs the CPU
    # forward at session setup, before looking at any target proposal.
    actions = []
    for variant, entry in enumerate(library["entries"]):
        for rid, root, _, ops in entry["sites"]:
            instructions = [[op, ins[0]] for op, ins in zip(ops, entry["program"][1], strict=True)]
            actions.append(dict(rule=rid, root=root, variant=variant, shape=entry["id"],
                                features=features(entry["program"]), instructions=instructions))
    return dict(target_sha256=library["target_sha256"], weights=checkpoint["weights"],
                mode="size" if largest else "ridge", candidates=actions)
