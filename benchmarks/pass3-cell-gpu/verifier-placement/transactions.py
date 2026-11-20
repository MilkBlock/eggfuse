"""Compare asking now and resolving a symbolic i64 guard at final verification on real port events."""
import argparse
from collections import Counter,defaultdict
import ctypes
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from matrix import HERE,load_rust
import subprocess


def compile_branches(packet,lits):
    """Find a one-constructor literal pattern paired with a greater-than guard at the same column."""
    equal={};greater={}
    for rid,rule in enumerate(packet['rules']):
        q=rule['q']
        if not q or not isinstance(q[0][0],int):continue
        table,args=q[0]
        if packet['tables'][table]['kind']!='constructor':continue
        variables=[v for v in args if v>=0]
        if len(set(variables))!=len(variables):continue
        if len(q)==1:
            literals=[i for i,v in enumerate(args[:-1]) if v<0]
            if len(literals)==1 and args[-1]>=0:
                i=literals[0];equal[(table,i,int(lits[-1-args[i]]))]=rid
        if len(q)==2 and q[1][0]=='>' and all(v>=0 for v in args):
            x,k,_=q[1][1]
            if x in args[:-1] and k<0:greater[(table,args.index(x),int(lits[-1-k]))]=rid
    return {key:(equal[key],greater[key]) for key in equal.keys()&greater.keys()
            if packet['tables'][key[0]]['schema'][key[1]]['name']=='i64'}


def collect(image,capture,neural=None):
    packet=json.loads((image/'ingress.json').read_bytes())
    with np.load(image/'device.npz') as z:lits=z['lits']
    contracts=compile_branches(packet,lits)
    if not contracts:raise RuntimeError('no matched integer branch pair')
    with np.load(capture/'output.npz') as z:rhs=z['rhs'];rows=z['rows']
    with np.load(capture/'neural-inputs.npz') as z:published=z['publications']
    won=set()
    if neural is not None:
        with np.load(neural/'neural-output.npz') as z:won.update(z['rhs_ordinal'].flatten())
        with np.load(neural/'compound-output.npz') as z:won.update(z['claims'][:,:,7].flatten())
    events=[]
    for ticket,(ordinal,effect,row,table) in enumerate(published,1):
        run,rid=map(int,rhs[ordinal-1,:2])
        for (t,col,threshold),branches in contracts.items():
            if t!=table:continue
            rule=packet['rules'][rid]
            # Recover the immutable numeric constructor argument from the actual producer binding.
            vals={v:int(rhs[ordinal-1,4+j]) for j,v in enumerate(rule['inputs'])}
            def value(arg):return int(lits[-1-arg]) if arg<0 else vals.get(arg)
            for op,fn,dst,args in rule['e'][:effect]:
                if op=='copy':vals[dst]=value(args[0])
                if op=='compute' and fn in ('+','-','*','min','max'):
                    x,y=map(value,args)
                    if x is not None and y is not None:
                        vals[dst]={'+':x+y,'-':x-y,'*':x*y,'min':min(x,y),'max':max(x,y)}[fn]
            op,fn,_,args=rule['e'][effect]
            assert op in ('construct','set') and fn==table
            arg=args[col];known=arg<0
            v=value(arg)
            if v is None:raise ValueError((rid,effect,'unsupported numeric operand'))
            assert v==rows[row,col]
            outcome=(1 if v==threshold else 2 if v>threshold else 0)
            literal=int(lits[-1-arg]) if known else None
            static_label=-1 if literal is None else (1 if literal==threshold else 2 if literal>threshold else 0)
            events.append((run,ticket,rid,int(effect),int(row),v,threshold,outcome,known,int(ordinal) in won,static_label))
    return np.array(events,dtype=np.int64),[(packet['tables'][k[0]]['name'],k[1],k[2],*v) for k,v in contracts.items()]


def entropy(values):
    freq=np.bincount(values,minlength=3)
    prob=freq[freq>0]/len(values)
    return -float((prob*np.log2(prob)).sum())


def kernel():
    load_rust()
    meta=json.loads(subprocess.check_output(['cargo','metadata','--no-deps','--format-version','1','--manifest-path',str(HERE/'Cargo.toml')]))
    lib=ctypes.CDLL(str(Path(meta['target_directory'])/'release/libcell_proof_verifier.dylib'))
    f=lib.compare_ports
    f.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p]
    f.restype=None
    return f


def study(a):
    f=kernel()
    splits=json.loads((a.corpus/'collection.json').read_bytes())
    # A fitted three-class categorical head over producer rule and effect port.
    training=defaultdict(lambda:np.ones(3))
    for name,case in splits.items():
        if case['split']!='train':continue
        events,_=collect(a.corpus/name/'input',a.train_capture/name)
        for _,_,rid,effect,_,_,_,label,_,_,_ in events:training[rid,effect][label]+=1
    results={}
    for name in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        image=a.ref/f'release-input-{name}' if name in ('sum-bits','dot-product') else a.corpus/name/'input'
        events,rules=collect(image,a.test_capture/name,a.online/f'{name}-1703-batch')
        epochs,tickets,rids,effects,addresses,values,thresholds,labels,static,neural,constants=events.T
        n=len(events);dynamic=np.flatnonzero(~static.astype(bool))
        ports=np.ascontiguousarray(np.stack([epochs,tickets,values],1))
        requests=np.ascontiguousarray(np.stack([np.arange(n),epochs,tickets,thresholds],1))
        def read(req):
            req=np.ascontiguousarray(req);out=np.empty(len(req),np.int64)
            f(ports.ctypes.data,len(ports),req.ctypes.data,len(req),out.ctypes.data)
            return out
        np.testing.assert_array_equal(read(requests),labels)
        stale=requests.copy();stale[:,2]-=1
        assert (read(stale)==-1).all()
        keys=sorted(set(training)|set(zip(map(int,rids),map(int,effects))))
        indices={key:i for i,key in enumerate(keys)}
        weights=torch.tensor(np.stack([np.log(training[key]) for key in keys]),dtype=torch.float32,device='mps')
        ids=torch.tensor([indices[int(r),int(k)] for r,k in zip(rids,effects)],device='mps')
        literal=torch.from_numpy(constants).to('mps')
        def predict():
            return torch.where(literal>=0,literal,weights[ids].argmax(1))
        cold=predict().cpu().numpy()
        np.testing.assert_array_equal(cold[static>0],labels[static>0])
        req_gpu=torch.from_numpy(requests).to('mps')
        groups=defaultdict(list)
        for pos in dynamic:groups[int(epochs[pos])].append(int(pos))
        epoch_blocks=[torch.tensor(pos,device='mps') for pos in groups.values()]
        single=[torch.tensor([int(pos)],device='mps') for pos in dynamic]
        def generate(mode):
            output=predict()
            if mode=='blind':return output.cpu().numpy()
            if mode=='deferred':
                # Rust evaluates the compiler's branch program on a sealed request list.
                return read(req_gpu.cpu().numpy())
            for ids in (single if mode=='individual' else epoch_blocks):
                replies=read(req_gpu[ids].cpu().numpy())
                output.index_copy_(0,ids,torch.from_numpy(replies).to('mps'))
            return output.cpu().numpy()
        samples=defaultdict(list)
        for i in range(9):
            order=['blind','deferred','epoch','individual'];order=order[i%3:]+order[:i%3]
            for mode in order:
                torch.mps.synchronize();start=perf_counter_ns();actual=generate(mode);torch.mps.synchronize()
                samples[mode].append((perf_counter_ns()-start)/1e6)
                np.testing.assert_array_equal(actual,cold if mode=='blind' else labels)
        by=defaultdict(list)
        for rid,k,b in zip(rids,effects,labels):by[int(rid),int(k)].append(int(b))
        conditional=sum(len(v)*entropy(np.array(v)) for v in by.values())/n
        results[name]=dict(events=n,rule_pairs=rules,static=int(static.sum()),dynamic=len(dynamic),epoch_batches=len(groups),
                           observed_neural_roots=int(neural.sum()),dynamic_neural_roots=int((neural*(1-static)).sum()),
                           labels=np.bincount(labels,minlength=3).tolist(),prior_errors=int((cold!=labels).sum()),
                           empirical_bits_given_producer_and_port=conditional,response_bits_needed=2,
                           prior_net_proposals=int((cold!=0).sum()),legal_branches=int((labels!=0).sum()),
                           corrected_branches=int((cold[dynamic]!=labels[dynamic]).sum()),invalidated_stale=len(stale),
                           ms=dict(samples),median_ms={k:median(v) for k,v in samples.items()})
        print(name,results[name]['events'],len(dynamic),results[name]['corrected_branches'],results[name]['median_ms'],flush=True)
        a.out.write_text(json.dumps(results,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('ref','corpus','train_capture','test_capture','online','out'):p.add_argument(k,type=Path)
    with torch.inference_mode():study(p.parse_args())
