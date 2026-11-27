"""Attribute complete native inter-publication intervals after the fixed schedule finishes."""

import json
import os
from collections import Counter, defaultdict
from time import perf_counter

import torch

from cell_kv_runtime import native
from continuous_stream import Stream
from continuous_trials import instrument, setup
from incremental_fit import output
from incremental_kv import InferenceCache
from incremental_native import Ledger, Pages
from partner_index_worlds import args


class Clock:
    def __init__(self):
        self.frames = []

    def append(self, f):
        self.frames.append((f["run"], perf_counter()))


class WindowPages(Pages):
    def __init__(self, w, pol):
        super().__init__(w, pol)
        self.windows = defaultdict(list)

    def append(self, row):
        super().append(row)
        self.windows[row[0]["run"]].append(self.rows[-1])


def run(a, case):
    for model in ("sweep", "A", "B", "C"):
        dest = output(a) / f"windows-{case}-{model}.json"
        if dest.exists():
            continue
        n, w, align = setup(a, case)
        if model != "sweep":
            n.load_state_dict(
                torch.load(output(a) / f"{case}-{model}-71-e3.pt", weights_only=True)
            )
        instrument(n, "exact")
        InferenceCache(n)
        policy = Stream(n, "A", incremental=False)
        log = WindowPages(w, policy)
        trace = Ledger()
        clock = Clock()
        r = native(
            a,
            w,
            policy=policy,
            seed=193,
            slots=6,
            submit_pages=2,
            receipt_log=log,
            receipt_memory=True,
            rule_state=True,
            execution_trace=trace,
            reference=align,
            publication_log=clock,
        )
        summary = defaultdict(Counter)
        for (run, start), (_, end) in zip(clock.frames, clock.frames[1:]):
            groups = log.windows[run]
            assert len(groups) == 2 and groups[0][0] == groups[1][0]
            entry = summary[groups[0][0]]
            entry["windows"] += 1
            entry["wall"] += end - start
            for _, ids, decode in groups:
                entry["decode"] += decode
                entry["external_paid"] += len(ids)
                entry["external_ops"] += sum(
                    trace.entries[i]["effective_ops"] for i in ids
                )
        dest.write_text(
            json.dumps(
                {
                    "result": r,
                    "windows": summary,
                    "native_digest": trace.response_digest,
                }
            )
        )
        print(dest.name, flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args(), os.environ["TR_CASE"])
