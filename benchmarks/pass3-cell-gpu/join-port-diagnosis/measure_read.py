"""Matched snapshot timing including typed key encoding and named packet materialization."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter
import numpy as np
import torch

from frozen_read import FrozenRead,float_read
from transfer import JoinReader


def encode(rows,delta,wm,bins,wide):
    states=np.array([(r,int(not delta or epoch>=wm)) for r,_,_,epoch in rows],dtype=np.int64)
    width=20 if wide else 4
    raw=b''.join(hashlib.sha256(json.dumps(key,sort_keys=True,separators=(',',':')).encode()).digest()[:width]
                 for _,key,_,_ in rows)
    codes=np.frombuffer(raw,dtype=np.uint8).reshape(-1,width)
    root=codes[:,:4]%bins if bins!=256 else codes[:,:4].copy()
    second=np.ascontiguousarray(codes[:,4:]).view("<u4") if wide else None
    return states,root,second


def reference(rows,delta,wm):
    buckets=defaultdict(list)
    for j,(role,key,_,_) in enumerate(rows):
        if role==1:
            buckets[json.dumps(key,sort_keys=True,separators=(',',':'))].append(j)
    return [(i,j) for i,(role,key,_,epoch) in enumerate(rows) if role==0
            for j in buckets.get(json.dumps(key,sort_keys=True,separators=(',',':')),())
            if not delta or max(epoch,rows[j][3])>=wm]


def run(cases,mode,model,baked,wide):
    encode_s=infer_s=pack_s=0.
    receipts=[]
    for c in cases:
        rows=c['rows']
        if not rows:
            receipts.append([])
            continue
        start=perf_counter()
        if mode=='reference':
            named=reference(rows,c['delta'],c['wm'])
            encoded=start
        else:
            state,codes,second=encode(rows,c['delta'],c['wm'],model.bins,wide)
            encoded=perf_counter()
            named=baked(state,codes,second) if mode=='baked' else float_read(model,state,codes,second)
        inferred=perf_counter()
        receipts.append([(rows[i][2],rows[i][3],rows[j][2],rows[j][3]) for i,j in named])
        encode_s+=encoded-start
        infer_s+=inferred-encoded
        pack_s+=perf_counter()-inferred
    return receipts,[encode_s,infer_s,pack_s,encode_s+infer_s+pack_s]


def main(a):
    torch.set_num_threads(1)
    model=JoinReader(32,True).eval()
    model.load_state_dict(torch.load(a.checkpoint,weights_only=True))
    baked=FrozenRead(model)
    results={}
    for bank in a.banks:
        cases=json.load(gzip.open(bank))
        modes=('reference','float','baked')
        times={k:[] for k in modes}
        truth,_=run(cases,'reference',model,baked,a.wide)
        original,_=run(cases,'float',model,baked,a.wide)
        observed,_=run(cases,'baked',model,baked,a.wide)
        if observed!=original:
            raise ValueError(f'{bank}: changed named packets during Bake')
        for r in range(3):
            for k in modes[r:]+modes[:r]:
                found,measure=run(cases,k,model,baked,a.wide)
                if found!=(truth if k=='reference' else original):
                    raise ValueError('non-repeatable output')
                times[k].append(measure)
        def handles(rows):
            return {json.dumps(v,sort_keys=True) for v in rows}
        missing=sum(len(handles(t)-handles(o)) for t,o in zip(truth,observed,strict=True))
        extra=sum(len(handles(o)-handles(t)) for t,o in zip(truth,observed,strict=True))
        results[bank.stem]=dict(cases=len(cases),target_pairs=sum(map(len,truth)),missing=missing,extra=extra,
                                matched_float=True,round_seconds=times,
                                median_total_seconds={k:median(row[-1] for row in v) for k,v in times.items()})
        print(bank.stem,results[bank.stem]['median_total_seconds'],missing,extra,flush=True)
        a.out.write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('checkpoint',type=Path)
    p.add_argument('out',type=Path)
    p.add_argument('banks',type=Path,nargs='+')
    p.add_argument('--wide',action='store_true',help='use a separate 128-bit confirmation view in the second learned read')
    main(p.parse_args())
