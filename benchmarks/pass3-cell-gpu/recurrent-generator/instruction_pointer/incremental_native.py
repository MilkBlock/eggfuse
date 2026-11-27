"""Independent fixed-generation trials, with post-Submit stratification and native ledger identity."""

import hashlib
import json
import os
from collections import Counter, defaultdict

import torch

from cell_kv_runtime import native
from continuous_stream import Stream
from continuous_trials import instrument, setup
from incremental_fit import output
from incremental_kv import InferenceCache
from partner_index_worlds import args
from trigger_execution import ExecutionTrace


def digest(x):
    return hashlib.sha256(
        json.dumps(x, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


class Ledger(ExecutionTrace):
    def response_history(self, records):
        self.response_digest = digest(records)


class Pages:
    def __init__(self, w, pol):
        self.world = w
        self.pol = pol
        self.rows = []
        self.previous = 0

    def append(self, row):
        s, _decisions, replies = row
        # After generation/submission, for reporting only. Never return a mask to the policy.
        tables = {p[3] for p in s["ports"]}
        roots = {self.world.layouts[t][0][0] for t in s["menu"]}
        constructible = [
            r for r in roots if all(t in tables for t in self.world.roles[r])
        ]
        active = (
            "empty"
            if not constructible
            else "active"
            if any(not s["check_dirty"] or s["rule_state"][r][1] for r in constructible)
            else "inactive"
        )
        elapsed = sum(self.pol.time[k] for k in ("state", "draw", "rebase"))
        self.rows.append((active, [r[0] for r in replies], elapsed - self.previous))
        self.previous = elapsed


def run_one(a, case, arm, seed, cap, checkpoint=None, worker=None):
    if worker is not None and checkpoint is not None:
        raise ValueError("shared batch worker uses the frozen sweep weights")
    n, w, align = setup(a, case)
    if checkpoint:
        n.load_state_dict(
            torch.load(output(a) / (checkpoint + ".pt"), weights_only=True)
        )
    times, calls = instrument(n, "exact")
    cache = InferenceCache(n) if arm != "ref" else None
    if worker:
        worker.install(n)
    pol = Stream(n, "A")
    pages = Pages(w, pol)
    trace = Ledger()
    r = native(
        a,
        w,
        policy=pol,
        seed=seed,
        slots=6,
        submit_pages=2,
        receipt_log=pages,
        receipt_memory=True,
        rule_state=True,
        execution_trace=trace,
        paid_limit=cap,
        reference=align,
    )
    buckets = defaultdict(Counter)
    for key, ids, elapsed in pages.rows:
        g = buckets[key]
        g["observed_pages"] += 1
        g["decode_seconds"] += elapsed
        g["issued"] += len(ids)
        g["ops"] += sum(trace.entries[uid]["effective_ops"] for uid in ids)
        for uid in ids:
            g[trace.entries[uid]["status"]] += 1
    return dict(
        r,
        case=case,
        arm=arm,
        seed=seed,
        cap=cap,
        checkpoint=checkpoint,
        native_digest=trace.response_digest,
        origins_digest=digest([trace.entries, trace.higher]),
        activity=buckets,
        cost=times,
        calls=calls,
        cache_counts=cache.count if cache else {},
        cache_seconds=cache.seconds if cache else {},
    )


def main(a, case):
    out = output(a)
    for model in os.getenv("IK_MODELS", "sweep").split():
        for seed in map(int, os.getenv("IK_DRAW", "193 307").split()):
            for cap in os.getenv("IK_CAP", "256 full").split():
                for arm in os.getenv("IK_METHODS", "ref cache").split():
                    path = (
                        out
                        / f"live-{case}-{model}-{arm}-{seed}-{cap}{os.getenv('IK_REP', '')}.json"
                    )
                    if path.exists():
                        continue
                    r = run_one(
                        a,
                        case,
                        arm,
                        seed,
                        None if cap == "full" else int(cap),
                        None if model == "sweep" else f"{case}-{model}",
                    )
                    path.write_text(json.dumps(r))
                    print(path.name, r["covered"], round(r["wall"], 2), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        main(args(), os.environ["TR_CASE"])
