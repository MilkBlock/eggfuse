"""Offline counterfactual action values with an identical signed prefix and equal paid horizon."""

import hashlib
import json
import os
import pickle

import numpy as np
import torch

from competition_draw import Page
from continuous_stream import Stream
from continuous_trials import output, run_native, setup
from partner_index_worlds import args


class Fork(Stream):
    def __init__(self, n, threshold, choice, tail_seed):
        super().__init__(n, "A")
        self.threshold = threshold
        self.choice = choice
        self.tail_rng = np.random.default_rng(tail_seed)
        self.anchor = None

    def generate(self, w, s, rng, slots):
        paid = len(s["request_receipts"])
        if self.anchor is None and paid >= self.threshold and s["menu"]:
            page = Page(self.net, w, s)
            # A separate RNG for candidate discovery, never advanced by the policy.
            options = page.draws(
                np.random.default_rng([paid, self.threshold, 71]), 3, True
            )
            if len(options) >= 2 and all(t is not None for t in options):
                self.anchor = {
                    "paid": paid,
                    "run": s["run"],
                    "epoch": s["epoch"],
                    "options": options,
                    "state": hashlib.sha256(pickle.dumps(s)).hexdigest(),
                    "logp": [
                        -float(self.net.token_loss(w, page.m, t)) for t in options
                    ],
                }
                return [options[self.choice]]
        return super().generate(
            w, s, self.tail_rng if self.anchor is not None else rng, slots
        )


def experiment(a, case):
    net, w, align = setup(a, case)
    rows = []
    for threshold in (5, 24, 48, 96, 144):
        probe = Fork(net, threshold, 0, 381)
        run_native(a, w, align, probe, 193, threshold + 32)
        if not probe.anchor:
            rows.append({"threshold": threshold, "unreached": True})
            continue
        cap = probe.anchor["paid"] + 1 + 24
        for tail in (381, 732):
            for i in range(len(probe.anchor["options"])):
                pol = Fork(net, threshold, i, tail)
                result, events, higher = run_native(a, w, align, pol, 193, cap)
                assert pol.anchor == probe.anchor and result["stats"]["paid"] == cap
                # Native UID also contains noncontiguous issuance identifiers. Use
                # the anchor's observed request and preserve the actual origin IDs.
                name = pol.anchor["options"][i]
                n_before = pol.anchor["paid"]
                # Internal steps are paid and can precede the chosen action.
                issued = sorted(
                    [r["uid"] for r in events]
                    + [s["uid"] for h in higher.values() for s in h["steps"]]
                )
                uid = issued[n_before]
                entry = next(r for r in events if r["uid"] == uid)
                assert (entry["tid"], entry["refs"]) == name
                origins = {r["uid"]: r["effective_ops"] for r in events}
                origins.update(
                    (s["uid"], s["effective_ops"])
                    for h in higher.values()
                    for s in h["steps"]
                )
                rows.append(
                    {
                        "threshold": threshold,
                        "tail": tail,
                        "choice": i,
                        "anchor": pol.anchor,
                        "cap": cap,
                        "status": entry["status"],
                        "immediate": origins[uid],
                        "future": sum(origins[x] for x in issued[n_before + 1 :]),
                        "ops": result["ops"],
                        "covered": result["covered"],
                        "facts": result["facts"],
                        "graph": result["graph"],
                    }
                )
        (output(a) / f"forks-{case}.json").write_text(json.dumps(rows))
        print(case, threshold, cap, flush=True)
    (output(a) / f"forks-{case}.json").write_text(json.dumps(rows))


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        experiment(args(), os.environ["TR_CASE"])
