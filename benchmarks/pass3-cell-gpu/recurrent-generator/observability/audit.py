"""Join pre-decision candidate observations to post-commit events without backdating winners."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np


def digest(*arrays):
    h=hashlib.sha256()
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def audit(e,name,rows):
    run=e/"compound-pending-pass3-v1/paired"/(name+"-1703-batch")
    capture=e/"recurrent-compositions-20261120"/name
    with np.load(run/"output.npz") as z: rhs=z["rhs"]
    with np.load(capture/"output.npz") as z: ref=z["rhs"]
    for cols in (slice(0,2),slice(4,None)):
        np.testing.assert_array_equal(rhs[:,cols],ref[:,cols])
    with np.load(capture/"neural-inputs.npz") as z:
        pub,feat=z["publications"],z["features"]
    with np.load(e/"recurrent-receipts-20261120"/name/"training.npz") as z:
        np.testing.assert_array_equal(feat,z["features"])
    with np.load(run/"neural-output.npz") as z: raw=z["raw"]
    with np.load(run/"compound-output.npz") as z: claims=z["claims"]
    stats=Counter(runs=len(raw),issued=int(np.count_nonzero(claims[:,:,8])))
    previous=np.zeros_like(raw[:,:2])
    previous[1:]=raw[:-1,2:]
    # Hash the entire root input, including previous self-generated latents.
    inputs=[digest(x,p) for x,p in zip(feat,previous)]
    bank=[digest(x[:,0],x[:1,1]) for x in feat]
    log=[]
    for i in range(len(raw)):
        log.append(dict(case=name,run=i+1,input=inputs[i],bank=bank[i],commits_before=int(np.searchsorted(rhs[:,0],i+1))))
    def expose(run_no, event):
        # Run numbers start at one. A post-Run event is visible at the next root decision.
        if run_no<len(log):
            log[run_no].setdefault("evidence_since_last_root",[]).append(event)
    for t,lane in zip(*np.nonzero(claims[:,:,4])):
        _,_,prod,row,ticket,_,_,_,status,*_=map(int,claims[t,lane])
        assert tuple(pub[ticket-1,:3])==(prod,int(raw[t,2+lane,10])-1,row)
        expose(int(rhs[prod-1,0]),["published",int(t+1),int(lane),ticket,row])
    failure_file=run/"claim-failure-times.npz"
    if failure_file.exists():
        with np.load(failure_file) as z: failures=z["failure_run"]
        assert failures.shape==claims.shape[:2]
        np.testing.assert_array_equal(failures>0,np.isin(claims[:,:,8],[3,4]))
        for t,lane in zip(*np.nonzero(failures)):
            when=int(failures[t,lane])
            assert int(t)+1<when<=len(raw)
            expose(when,["invalidated" if claims[t,lane,8]==3 else "duplicate",int(t+1),int(lane)])
    else:
        stats["untimed_failures"]=int(np.isin(claims[:,:,8],[3,4]).sum())
    for t,lane in zip(*np.nonzero(claims[:,:,7])):
        parent,j,producer,row,ticket,boundary,_,win,status,*_=map(int,claims[t,lane])
        assert status==6 and boundary==rhs[win-1,0] and row==rhs[win-1,3]
        assert tuple(pub[ticket-1,:3])==(producer,int(raw[t,2+lane,10])-1,row)
        assert (t+1)==rhs[producer-1,0]<boundary
        expose(boundary,["committed",int(t+1),int(lane),ticket,win])
        leaf=int(raw[t,2+lane,8])-1
        # Restrict to the lifetime of this precise publication. Another
        # publication even to the same row can replace the ticket.
        later=pub[ticket:]
        rep=np.flatnonzero(later[:,2]==row)
        end=int(rhs[later[rep[0],0]-1,0]) if len(rep) else len(raw)
        at=boundary-1
        slots=np.flatnonzero(feat[at,leaf*8:leaf*8+8,0]==row)
        stats["winning_children"]+=1
        if not len(slots):continue
        stats["winner_in_root_bank"]+=1
        pairs=[]
        for k in range(boundary,end):
            if row not in feat[k,leaf*8:leaf*8+8,0]:continue
            pairs.append(k)
        if pairs:
            stats["winners_reoffered"]+=1
            stats["candidate_pairs"]+=len(pairs)
        for k in pairs:
            stats["same_entire_bank"]+=bank[k]==bank[at]
            stats["identical_actor_input"]+=inputs[k]==inputs[at]
        log[at].setdefault("wins_later_this_run",[]).append([int(t+1),int(lane),ticket,win])
        for k in pairs:
            log[k].setdefault("prior_win_for_candidate",[]).append([leaf,row,ticket,win,boundary])
    rows.extend(log)
    return dict(stats)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("experiments",type=Path);p.add_argument("output",type=Path)
    a=p.parse_args();a.output.mkdir(exist_ok=True)
    rows=[]
    results={name:audit(a.experiments,name,rows) for name in ("sum-bits","dot-product","gemm-bias-relu","stable-argmax")}
    (a.output/"results.json").write_text(json.dumps(results,indent=2)+"\n")
    with (a.output/"decisions.jsonl").open("w") as f:
        for r in rows:f.write(json.dumps(r)+"\n")
    print(results)
