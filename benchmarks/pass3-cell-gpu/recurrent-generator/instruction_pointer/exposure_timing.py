"""Alternating complete native executions at equal paid caps, grouped by actual graph for ratios."""
import json
import os
from time import time

import torch

from exposure_data import observed
from exposure_eval import Database, SourcePanic, Trials
from exposure_train import output
from int_parameters import digest
from partner_index_worlds import args


def run(a):
    db=Database(output(a)/"native.sqlite")
    # Final timing is separate from corpus construction, fit and epoch selection.
    for case in ("sum-divisors","shared-polynomial","crossed-difference"):
        for seed in (193,307):
            for names,unique in ((("random","A/local-s71-t1000000"),(True,True)),
                                 (("A/local-s71-t1000000","A/local-s71-t1000000"),(False,True))):
                if not all(unique) and case!="sum-divisors":
                    continue
                trials=[Trials(a,db,case,n,seed,u) for n,u in zip(names,unique,strict=True)]
                key=digest([t.condition for t in trials])
                if db.get("timing",key) is not None or db.get("timing_failure",key) is not None:
                    continue
                try:
                    references = [t.trial(256) for t in trials]
                except SourcePanic as error:
                    db.put("timing_failure", key, dict(conditions=[t.condition for t in trials],
                                                       cap=256, stderr=error.evidence["stderr"]))
                    continue
                rows=[]
                for rep in range(4):
                    for index in ((0,1) if rep%2==0 else (1,0)):
                        t=trials[index]
                        r,tr=observed(t.w,t.align,a,t.policy,t.seed,256)
                        ref=references[index]
                        if (r["graph"]!=ref["r"]["graph"] or r["facts"]!=ref["r"]["facts"]
                            or [q[-1] for q in tr.responses]!=[tuple(q["reply"]) for q in ref["requests"]]):
                            raise ValueError("timing run does not reproduce the paid-prefix receipts and graph")
                        rows.append(dict(**t.condition,rep=rep,index=index,ops=r["ops"],paid=r["stats"]["paid"],
                                         wall=r["wall"],eps=r["eps"],ept=r["ept"],graph=r["graph"],facts=r["facts"]))
                db.put("timing",key,rows)


if __name__=="__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
