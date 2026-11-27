"""Measure fitted CE on actual exposures and probability shifts after verified accepted work."""

import gzip
import json
import pickle
import random
from collections import defaultdict

import torch

from cell_kv_runtime import native
from cell_transaction import STATUS
from feedback_measure import prob
from feedback_stall import folder
from int_parameters import digest
from joint_cell_sweep import complete_ce
from partner_index_worlds import args
from scaling_archive import directory
from scaling_eval import frozen
from scaling_fit import atomic, save_seen
from scaling_pool import Pool
from scaling_transitions import Replay
from state_transition_corpus import world


def receipts(a, actor):
    pairs = []
    for i in range(6):
        w = world(a, actor, i, False)
        raw = pickle.loads((folder(a) / f"test-{i}.pkl").read_bytes())
        for mid, remaining, done, statuses in raw["mids"]:
            if done not in raw["orig"] or STATUS[statuses[done][1]] != "duplicate":
                continue
            log = []
            native(
                a,
                w,
                policy=Replay([[done]]),
                seed=9541 + i,
                slots=6,
                submit_pages=2,
                receipt_log=log,
                rule_state=True,
                receipt_memory=True,
            )
            before, after = log[0][0], log[1][0]
            if (
                any(after[k] != v for k, v in mid.items())
                or before["ports"] != after["ports"]
                or set(remaining) != raw["orig"].keys() - {done}
            ):
                raise ValueError(
                    "before/after decision state differs from audited causal pair"
                )
            pairs.append((i, w, before, after, done, sorted(remaining)))
    return pairs


def collect(a):
    d = directory(a)
    out = d / "postfit.json"
    results = json.loads(out.read_text()) if out.exists() else {}
    n = frozen(a, "initial")[0]
    pool = Pool(a, n, True)
    pairs = receipts(a, n.actor)
    for resume in (d / "fits").glob("*-resume.pt"):
        name = resume.name.removesuffix("-resume.pt")
        candidates = list((d / "fits").glob(f"{name}-t*.json"))
        missing = [
            p for p in candidates if not (p.parent / (p.stem + ".seen.gz")).exists()
        ]
        if missing:
            progress = torch.load(resume, weights_only=False)["progress"]
            stem = f"{name}-t{progress[4]}"
            if any(p.stem == stem for p in missing):
                save_seen(resume.parent, stem, progress[0])
    names = [
        "initial",
        "sweep",
        *sorted(
            p.name.removesuffix(".seen.gz") for p in (d / "fits").glob("*.seen.gz")
        ),
    ]
    for name in names:
        if name in results:
            continue
        n = frozen(a, name)[0]
        seen_probe = []
        members = d / "fits" / (name + ".seen.gz")
        if members.exists():
            with gzip.open(members, "rb") as f:
                coverage = pickle.load(f)
            sources = defaultdict(list)
            for k in sorted(coverage):
                sources[pool.records[k]].append(k)
            rng = random.Random(27501)
            for source, ks in sorted(sources.items()):
                for k in rng.sample(ks, min(8, len(ks))):
                    w, s, _ = pool.row(k)
                    n.prepare(w)
                    available = sorted(coverage[k])
                    ts = rng.sample(available, min(32, len(available)))
                    ce = float(complete_ce(n, w, n.state(w, s), ts))
                    seen_probe.append([source, k, len(ts), ce])
        changes = []
        for i, w, before, after, done, others in pairs:
            n.prepare(w)
            domain = [done, *others]
            p, q = prob(n, w, before, domain), prob(n, w, after, domain)
            changes.append(
                [
                    i,
                    digest(after),
                    p[done],
                    q[done],
                    sum(p[t] for t in others),
                    sum(q[t] for t in others),
                ]
            )
        results[name] = {"seen": seen_probe, "changes": changes}
        atomic(out, results)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        collect(args())
