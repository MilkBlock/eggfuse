"""Native replay corpus for full-token CE and correct-template forks."""

import json
import os
import pickle
from collections import Counter, defaultdict

import numpy as np
import torch

from binding_packets import public_view
from completion_context import native, read
from discrete_cells import from_q
from multirule_support import features
from partner_index_worlds import args, frozen
from query_environment import conditioned
from recursive_train import folder


@torch.no_grad()
def collect(a, model, case, d, tape, out):
    if not tape.exists():
        native(a, d, "capture", tape)
    replay = native(
        a,
        d,
        "replay",
        tape,
        "--memory",
        out / "frames",
        "--ept-origins",
        env=dict(os.environ, EGGFUSE_QUERY_OBSERVER=str(out / "observer")),
    )
    origins = dict(replay["ept"]["origins"])
    m = conditioned(a, d, out / "observer")
    prog = read(d / "program.json")
    groups = defaultdict(lambda: defaultdict(list))
    for q in read(tape)["requests"]:
        if origins.get(q["token"], 0) > 0:
            groups[q["run"]][q["rule"]].append(q)
    rng = np.random.default_rng(123)
    selected = (
        set(rng.choice(sorted(groups), min(40, len(groups)), replace=False).tolist())
        if groups
        else set()
    )
    examples = []
    counts = Counter()
    prevdirty = {}
    versions = {}
    try:
        for line in (out / "frames").open():
            f = json.loads(line)
            if f.get("final_publication"):
                continue
            m.update(f)
            run = f["run"]
            dirty = {r: bool(m.rule_features[m.rule_index[r], 0]) for r in m.rule_ids}
            wake = sum(v and prevdirty.get(r) is False for r, v in dirty.items())
            prevdirty.update(dirty)
            changed = 0
            for addr, port in f["updates"]:
                key = addr["token"], addr["op"]
                changed += key in versions and versions[key] != port["version"]
                versions[key] = port["version"]
            if run not in selected:
                continue
            ids = [r for r, h in m.ids if not h]
            feat = tuple(x.cpu() for x in features(model, m, prog, run))
            candidates = list(groups[run])
            rng.shuffle(candidates)
            for rid in candidates[:4]:
                qs = groups[run][rid]
                z = public_view(m, prog, key=(rid, False)) if m.roles[rid] else None
                g = []
                for ind in rng.choice(len(qs), min(len(qs), 6), replace=False):
                    c = from_q(qs[ind])
                    g.append(
                        [
                            bank.index(v)
                            for bank, v in zip(z["addrs"], c.refs, strict=True)
                        ]
                        if z
                        else []
                    )
                if z:
                    z = dict(z, banks=[dict(b, last=-1) for b in z["banks"]])
                examples.append(
                    {
                        "case": case,
                        "run": run,
                        "features": feat,
                        "rid": rid,
                        "target": ids.index(rid),
                        "z": z,
                        "g": g,
                        "owners": len(m.pub.live),
                        "wake": wake,
                        "versions": changed,
                        "retired": len(f["retired"]),
                        "repairs": len(f["repair_events"]),
                    }
                )
                counts["tokens"] += len(g)
    finally:
        m.close_observer()
    with (out / "examples.pkl").open("wb") as w:
        pickle.dump(examples, w, protocol=5)
    print(case, len(examples), counts, flush=True)


def main(a):
    m = frozen(a, a.seeds[0])
    for case, d in [
        (f"dynamic-{i}", a.previous / "programs" / f"{i:04d}") for i in range(12)
    ] + [(c, folder(a.data, c)) for c in ("fact", "loopfact", "sum-divisors")]:
        out = a.out / "corpus" / case
        out.mkdir(parents=True, exist_ok=True)
        collect(
            a,
            m,
            case,
            d,
            d / "tape.json" if (d / "tape.json").exists() else out / "teacher.json",
            out,
        )


if __name__ == "__main__":
    torch.set_num_threads(1)
    main(args())
