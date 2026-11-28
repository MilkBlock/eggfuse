"""Fixed inner validation probes with the original complete-token CE and native sibling pairs."""
import os

import torch

from exposure_eval import Database
from exposure_policy import policy
from exposure_train import output
from int_parameters import digest
from partner_index_worlds import args
from scaling_counterfactual import recover
from scaling_eval import probes


def run(a):
    db = Database(output(a) / "native.sqlite")
    for name in os.getenv("EXPOSURE_MODELS","local-s71-t100000").split():
        if db.get("probes",name):
            continue
        n = policy(a,"loopfact",name)[0].net
        rows = probes(a,n)
        pairs = []
        for i,w,targets in recover(a,n.actor):
            n.prepare(w)
            for s,(tid,refs) in targets:
                m = n.state(w,s)
                scores = {t:float((-n.token_loss(w,m,(t,refs))).exp())
                          for t in range(w.primitives,len(w.layouts))}
                pairs.append(dict(program=i,state=digest(s),target=tid,full=scores[tid],
                                  probability=scores,wins=scores[tid]>max(p for t,p in scores.items() if t!=tid)))
        db.put("probes",name,dict(binding=rows,higher=pairs))


if __name__=="__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
