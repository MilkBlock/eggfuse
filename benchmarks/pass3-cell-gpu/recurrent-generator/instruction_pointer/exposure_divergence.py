"""Separate the first divergence in proposals from the first difference in native work."""
import os
from contextlib import nullcontext

import numpy as np
import torch

from exposure_data import branch, observed
from exposure_eval import Database, Trials
from exposure_policy import policy
from exposure_train import output
from int_parameters import digest
from partner_index_worlds import args


class AuditTrace:
    def __init__(self, pol):
        self.pol, self.pages, self.states = pol, [], []

    def prepare(self, w):
        self.pol.prepare(w)

    def inference_session(self):
        return self.pol.inference_session() if hasattr(self.pol, "inference_session") else nullcontext()

    def observe_publication(self, frame):
        self.pol.observe_publication(frame)

    def generate(self, w, s, rng, slots):
        page = self.pol.generate(w, s, rng, slots)
        self.states.append(s)
        self.pages.append(page)
        return page


def audit(a, name, case, seed):
    path = output(a)
    db = Database(path / "native.sqlite")
    trials = [Trials(a, db, case, arm, seed, True) for arm in (name, "random")]
    key = digest([t.condition for t in trials])
    if db.get("divergence", key) is not None:
        return
    logs = []
    cumulative = []
    for t in trials:
        trace = AuditTrace(t.policy)
        r, _ = observed(t.w, t.align, a, trace, seed, 257)
        x = t.trial(257)
        if r["graph"] != x["r"]["graph"] or r["facts"] != x["r"]["facts"]:
            raise ValueError("diagnostic tap changed independent execution")
        logs.append(trace)
        cumulative.append(np.cumsum([q["ops"] for q in x["requests"]]))
    diff = next((i for i, (l,r) in enumerate(zip(*cumulative)) if l != r), None)
    by_paid = None
    if diff is not None:
        by_paid = dict(paid=diff + 1, ops=[int(v[diff]) for v in cumulative],
                       requests=[t.trial(257)["requests"][diff] for t in trials])
    for i,(left,right) in enumerate(zip(*(g.pages for g in logs))):
        if left == right:
            continue
        s = logs[0].states[i]
        if s != logs[1].states[i]:
            raise ValueError("first differing proposals were not generated in a common state")
        w, align = trials[0].w, trials[0].align
        prefix = logs[0].pages
        blank, graph, _ = branch(a, w, align, prefix, i, s, None, seed)
        forks = []
        for token in sorted(set(left + right)):
            facts, result, evidence = branch(a,w,align,prefix,i,s,token,seed)
            forks.append(dict(token=token, neural=token in left, random=token in right,
                              graph=result, gain=sorted(facts-blank),lost=sorted(blank-facts), **evidence))
        previous = len(s["request_receipts"])
        db.put("divergence",key,dict(model=name,case=case,seed=seed,page=i,run=s["run"],
               state=digest(s),epoch=s.get("epoch"),prior_paid=previous,
               prior_paid_operations=int(cumulative[0][previous-1]) if previous else 0,
               neural=left, random=right,blank_graph=graph,forks=forks,first_different_credit=by_paid))
        return
    raise ValueError("no differing proposal in paired trajectories")


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        a=args()
        for name in os.getenv("EXPOSURE_MODELS","local-s71-t100000").split():
            for seed in (193,307):
                audit(a,name,"sum-divisors",seed)
