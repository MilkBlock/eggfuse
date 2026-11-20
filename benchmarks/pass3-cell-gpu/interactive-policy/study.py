"""Does an immediate typed reply improve the next learned choice on authentic source publications?"""
import argparse
from collections import Counter,defaultdict
import ctypes
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
import tempfile
from time import perf_counter_ns

import numpy as np
import torch

from corpus import HERE,Ports,read_ports,later_labels,neural_origin,observable_features
from policy import features_reply,train

MODES=('blind','guard','value','both-values','deferred')


class Native:
    def __init__(self,where):
        manifest=HERE.parent/'verifier-placement/Cargo.toml'
        subprocess.run(['cargo','build','--release','--locked','--manifest-path',str(manifest)],check=True)
        meta=json.loads(subprocess.check_output(['cargo','metadata','--no-deps','--format-version','1','--manifest-path',str(manifest)]))
        self.guard=ctypes.CDLL(str(Path(meta['target_directory'])/'release/libcell_proof_verifier.dylib')).compare_ports
        self.guard.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p]
        self.guard.restype=None
        path=where/'libtyped_read.dylib'
        subprocess.run(['rustc','--edition','2021','--crate-type','cdylib','-C','opt-level=3',
                        str(HERE/'typed_read.rs'),'-o',str(path)],check=True)
        self.value=ctypes.CDLL(str(path)).read_i64
        self.switch=ctypes.CDLL(str(path)).deferred_switch
        self.switch.restype=None
        self.switch.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,
                              ctypes.c_void_p,ctypes.c_void_p]
        self.value.restype=None
        self.value.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p]

    def request(self,ledger,visible,requests,kind):
        req=np.ascontiguousarray(requests,dtype=np.int64)
        answer=np.empty((len(req),2) if kind=='value' else len(req),np.int64)
        fn=self.value if kind=='value' else self.guard
        fn(ledger.ctypes.data,visible,req.ctypes.data,len(req),answer.ctypes.data)
        return answer


class Replay:
    def __init__(self,ports,vocab,device):
        self.events=e=ports.events;self.device=device
        self.ledgers=[np.ascontiguousarray(e[:,[0,1,c]]) for c in (5,6)]
        self.ids,self.features=[torch.as_tensor(a,device=device) for a in observable_features(e,vocab)]
        positions=np.arange(len(e))
        address=np.stack([positions,e[:,0],e[:,1]],1)
        self.requests=torch.tensor(address,device=device)
        self.bounds=[(g[0],g[-1]+1) for g in np.split(positions,np.flatnonzero(np.diff(e[:,0]))+1) if len(g)]
        self.zero_guard=np.where(e[:,9],np.where(e[:,5]==e[:,7],1,np.where(e[:,5]>e[:,7],2,0)),-1)
        self.zero_b=np.where(e[:,9],e[:,5],0);self.zero_a=np.where(e[:,10],e[:,6],0)

    def run(self,net,mode,native,stale=False,return_scores=False):
        e=self.events;device=self.device
        score=[];transactions=words=0
        for lo,hi in self.bounds:
            X=e[lo:hi]
            context=net.context(self.ids[lo:hi],self.features[lo:hi])
            g=self.zero_guard[lo:hi].copy();b=self.zero_b[lo:hi].copy();a=self.zero_a[lo:hi].copy()
            def fetch(mask,ledger,kind):
                nonlocal transactions,words
                # Handles travel from the model device to the Rust verifier. The slice
                # bound prevents requests from reading beyond the current source epoch.
                ix=np.flatnonzero(mask)
                req=self.requests[lo:hi].index_select(0,torch.as_tensor(ix,device=device)).cpu().numpy().copy()
                if stale:req[:,2]-=1
                if kind=='guard':req=np.column_stack([req,X[ix,7]])
                transactions+=len(req);words+=len(req)*(req.shape[1]+(2 if kind=='value' else 1))
                return ix,native.request(self.ledgers[ledger],hi,req,kind)
            m={'blind':0,'deferred':0,'guard':1,'value':2,'both-values':3}[mode]
            dynamic=X[:,9]==0
            if m==1 and dynamic.any():
                ix,ans=fetch(dynamic,0,'guard');g[ix]=ans
            if m>=2 and dynamic.any():
                ix,ans=fetch(dynamic,0,'value');ok=ans[:,0].astype(bool)
                if not ok.all():raise ValueError('unexpected invalid payload')
                b[ix]=ans[:,1];g[ix]=np.where(b[ix]==X[ix,7],1,np.where(b[ix]>X[ix,7],2,0))
            if m==3 and np.any(X[:,10]==0):
                ix,ans=fetch(X[:,10]==0,1,'value')
                if not ans[:,0].all():raise ValueError('invalid sibling payload')
                a[ix]=ans[:,1]
            reply=features_reply(X,m,g,b,a)
            score.append(net.decide(context,torch.tensor(reply,device=device)))
        logits=torch.cat(score)
        # Primary gate, primary branch selector, additional consumer gate.
        actions=(logits>0).cpu().numpy()
        raw=actions.copy()
        predicted=np.stack([actions[:,0]&~actions[:,1],actions[:,0]&actions[:,1],actions[:,2]],1)
        if mode=='deferred':
            # The symbolic primary is only resolved if it was actually emitted.
            # The immutable per-publication ledger must survive until this point.
            g=self.zero_guard.copy()
            ix=np.flatnonzero((e[:,9]==0)&actions[:,0])
            if len(ix):
                req=self.requests.index_select(0,torch.tensor(ix,device=device)).cpu().numpy()
                req=np.column_stack([req,e[ix,7]])
                g[ix]=native.request(self.ledgers[0],len(e),req,'guard')
                transactions+=len(req);words+=len(req)*5
            predicted[:,0]=actions[:,0]&(g==1);predicted[:,1]=actions[:,0]&(g==2)
        outcome=(predicted,raw,transactions,words*8)
        return (*outcome,logits.cpu().numpy()) if return_scores else outcome


def metrics(y,count,p,raw):
    good=p&y;extras=p&~y;missing=y&~p
    nonempty=y.any(1);correct=(y==p).all(1)
    return dict(ports=len(y),consumed=int(nonempty.sum()),future_rhs=int(count.sum()),distinct_consumers=int(y.sum()),
                selected=int(p.sum()),true_distinct=int(good.sum()),unobserved=int(extras.sum()),missed=int(missing.sum()),
                correct_complete=int(correct.sum()),complete_nonempty=int((nonempty&correct).sum()),
                actual_primary=int(y[:,:2].sum()),predicted_primary=int(p[:,:2].sum()),matched_primary=int(good[:,:2].sum()),
                actual_optional=int(y[:,2].sum()),predicted_optional=int(p[:,2].sum()),matched_optional=int(good[:,2].sum()),
                primary_issue_decisions=int(raw[:,0].sum()),extra_issue_decisions=int(raw[:,2].sum()),
                source_ordinals_beyond_one_per_port_consumer=int(count.sum()-y.sum()))


def changes(baseline,variant,y):
    old,raw_old=baseline;new,raw_new=variant
    old_ok=(old==y).all(1);new_ok=(new==y).all(1)
    return dict(changed_output_ports=int((old!=new).any(1).sum()),
                changed_primary_gate=int((raw_old[:,0]!=raw_new[:,0]).sum()),
                changed_optional_gate=int((raw_old[:,2]!=raw_new[:,2]).sum()),
                corrected_complete=int((~old_ok&new_ok).sum()),lost_complete=int((old_ok&~new_ok).sum()))


def information(events,y):
    masks=y.astype(int)@np.array([1,2,4])
    g=np.where(events[:,5]==events[:,7],1,np.where(events[:,5]>events[:,7],2,0))
    def conditional(arrays):
        groups=defaultdict(list)
        for vals,target in zip(zip(*arrays),masks):groups[vals].append(int(target))
        bits=best=0.
        for values in groups.values():
            counts=np.array(list(Counter(values).values()));freq=counts/len(values)
            bits-=len(values)*float(freq@np.log2(freq));best+=counts.max()
        return dict(bits=bits/len(events),hindsight_majority_exact=int(best),groups=len(groups))
    return {name:conditional(cols) for name,cols in {
            'guard':[g], 'producer_port':[events[:,2],events[:,3]], 'producer_port_guard':[events[:,2],events[:,3],g],
            'producer_port_value':[events[:,2],events[:,3],events[:,5]],'both_values':[events[:,5],events[:,6]]}.items()}


def outcome_table(events,y):
    guard=np.where(events[:,5]==events[:,7],1,np.where(events[:,5]>events[:,7],2,0))
    masks=y.astype(int)@np.array([1,2,4])
    return {str(k):dict(Counter(map(int,masks[guard==k]))) for k in (0,1,2)}


def evaluate(net,vocab,native,ports,truth,counts,device,reps,schedule,all_ports,selected):
    replay=Replay(ports,vocab,device);net=net.to(device)
    outputs={};report={};durations={m:[] for m in MODES}
    for m in MODES:
        pred,raw,nreq,traffic=replay.run(net,m,native);outputs[m]=pred,raw
        report[m]=dict(metrics(truth,counts,pred,raw),requests=nreq,payload_bytes=traffic)
    for repeat in range(reps):
        order=MODES[repeat%len(MODES):]+MODES[:repeat%len(MODES)]
        for m in (order if repeat%2==0 else order[::-1]):
            if device=='mps':torch.mps.synchronize()
            start=perf_counter_ns();p,r,nreq,traffic=replay.run(net,m,native)
            if device=='mps':torch.mps.synchronize()
            durations[m].append((perf_counter_ns()-start)/1e6)
            np.testing.assert_array_equal(outputs[m][0],p);np.testing.assert_array_equal(outputs[m][1],r)
    for m in MODES:
        report[m]['paired_ms']=durations[m];report[m]['median_ms']=median(durations[m])
        report[m]['vs_blind']=changes(outputs['blind'],outputs[m],truth)
        report[m]['vs_deferred']=changes(outputs['deferred'],outputs[m],truth)
    # Remove every observation after a real source epoch; rerun the first half
    # from scratch. Later source publications must not affect issuing decisions.
    cutoff=replay.bounds[len(replay.bounds)//2][1]
    prefix=Replay(Ports(ports.events[:cutoff],ports.branches,ports.optional),vocab,device)
    for m in MODES:
        p,r,_,_=prefix.run(net,m,native)
        np.testing.assert_array_equal(outputs[m][0][:cutoff],p)
        np.testing.assert_array_equal(outputs[m][1][:cutoff],r)
        report[m]['prefix_without_future_ports_verified']=int(cutoff)
    # A stale guard and masked reply have the exact same inputs for dynamic ports.
    p,r,_,_=replay.run(net,'guard',native,stale=True)
    np.testing.assert_array_equal(p,outputs['blind'][0]);np.testing.assert_array_equal(r,outputs['blind'][1])
    np.testing.assert_array_equal(outputs['blind'][1],outputs['deferred'][1])
    if not (ports.events[:,9]==0).any():
        for m in ('guard','value'):
            np.testing.assert_array_equal(outputs[m][1],outputs['blind'][1])
            assert report[m]['requests']==0
    fixed_guard=(ports.events[:,5,None]==ports.events[:,7,None])
    compiled=np.concatenate([fixed_guard,ports.events[:,5,None]>ports.events[:,7,None],np.zeros_like(fixed_guard)],1)
    report['compiler_all_primary']=metrics(truth,counts,compiled,np.column_stack([compiled[:,:2].any(1),compiled[:,1],compiled[:,2]]))
    for arm,raw in [('native-deferred',outputs['blind'][1]),('native-deferred-all',np.ones_like(outputs['blind'][1]))]:
        # Other source publications still update the authoritative ledger when only
        # neural-origin decisions are measured. The neural head cannot read them.
        claims=np.zeros((len(all_ports),2),np.int64);claims[selected]=raw[:,[0,2]]
        ans=np.empty((len(claims),4),np.int64)
        times=[]
        for _ in range(reps):
            begin=perf_counter_ns()
            native.switch(all_ports.ctypes.data,len(all_ports),schedule.ctypes.data,len(schedule),claims.ctypes.data,ans.ctypes.data)
            times.append((perf_counter_ns()-begin)/1e6)
        total=[]
        for _ in range(reps):
            if device=='mps':torch.mps.synchronize()
            begin=perf_counter_ns()
            if arm=='native-deferred':
                _,issued,_,_=replay.run(net,'blind',native)
                claims[selected]=issued[:,[0,2]]
            native.switch(all_ports.ctypes.data,len(all_ports),schedule.ctypes.data,len(schedule),claims.ctypes.data,ans.ctypes.data)
            if device=='mps':torch.mps.synchronize()
            total.append((perf_counter_ns()-begin)/1e6)
        pred=ans[selected,:3].astype(bool);when=ans[selected,3]
        report[arm]=dict(metrics(truth,counts,pred,raw),superseded_before_next_run=int((when<0).sum()),
                         superseded_but_later_source_consumed=int(((when<0)&truth.any(1)).sum()),
                         same_port_version=int((when>0).sum()),no_later_scheduled_run=int((when==0).sum()),
                         rust_segment_ms=times,median_rust_segment_ms=median(times),combined_ms=total,median_combined_ms=median(total))
        outputs[arm]=pred,raw
    for m,(pred,_) in outputs.items():
        b,k=ports.events[:,5],ports.events[:,7]
        report[m]['primary_guard_impossible']=int(((pred[:,0]&(b!=k))|(pred[:,1]&(b<=k))).sum())
        report[m]['optional_literal_impossible']=int((pred[:,2]&(ports.events[:,6]!=ports.events[:,8])).sum())
    return report,outputs


def phase(a):
    torch.set_num_threads(1)
    collection=json.loads((a.families/'collection.json').read_bytes())
    training={}
    for name,meta in collection.items():
        if meta['split']=='train':
            cap=a.train_capture/name;ports=read_ports(a.families/name/'input',cap)
            training[name]=(ports,later_labels(cap,ports)[0])
    assert len(training)==4
    a.out.mkdir(parents=True,exist_ok=False)
    result=dict(train={k:len(p.events) for k,(p,_) in training.items()},learned={},scope='post-publication decision replay')
    with tempfile.TemporaryDirectory() as tmp:
        native=Native(Path(tmp))
        data=np.array([[17,50,2**63-1],[17,51,-2**63]],dtype=np.int64)
        req=np.array([[0,17,50],[1,17,51],[0,16,50],[0,17,51],[-1,17,50],[2,17,52]],dtype=np.int64)
        np.testing.assert_array_equal(native.request(data,2,req,'value'),[[1,2**63-1],[1,-2**63],[0,0],[0,0],[0,0],[0,0]])
        rep=native.request(data,2,np.column_stack([req,np.zeros(len(req),np.int64)]),'guard')
        np.testing.assert_array_equal(rep,[2,0,-1,-1,-1,-1])
        for seed in a.seeds:
            net,vocab,losses=train(training,seed,a.updates)
            path=a.out/f'policy-{seed}.pt';torch.save(net.state_dict(),path)
            rec=dict(samples={},trainable_parameters=sum(p.numel() for p in net.parameters()),
                     loss_every_75=losses,state_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            result['learned'][seed]=rec
            with torch.inference_mode():
                for name in a.cases:
                    image=a.ref/f'release-input-{name}' if name in ('sum-bits','dot-product') else a.families/name/'input'
                    cap=a.capture/name;ports=read_ports(image,cap)
                    truth,counts,first=later_labels(cap,ports)
                    packet=json.loads((image/'ingress.json').read_bytes())
                    eligible=[i for i,(_,ids) in enumerate(packet['sets'].items())
                              if set((*ports.branches,ports.optional)).issubset(ids)]
                    if not eligible:raise ValueError('no source ruleset schedules these consumers')
                    # The native replay receives these Run events when they occur. The
                    # neural issuer never receives the schedule or future consumption labels.
                    with np.load(cap/'output.npz') as z:schedule=np.isin(z['runs'][:,0],eligible).astype(np.int64)

                    origin=neural_origin(cap,a.online/f'{name}-{seed}-batch',ports)
                    for cohort,select in [('source',np.ones(len(origin),bool)),('neural',origin)]:
                        e=ports.events[select];sub=Ports(e,ports.branches,ports.optional);y=truth[select];att=counts[select]
                        if len(e)==0:continue
                        row=dict(primary_rules=ports.branches,optional=ports.optional,ports=len(e),dynamic_b=int((e[:,9]==0).sum()),
                                 dynamic_a=int((e[:,10]==0).sum()),epochs=len(np.unique(e[:,0])),information=information(e,y),
                                 outcomes=outcome_table(e,y),devices={})
                        canonical=None
                        for device in ('cpu','mps'):
                            s,output=evaluate(net,vocab,native,sub,y,att,device,a.repeats,schedule,ports.events,select)
                            row['devices'][device]=s
                            if canonical is None:canonical=output
                            else:
                                for m in MODES:
                                    for before,now in zip(canonical[m],output[m]):np.testing.assert_array_equal(before,now)
                        rec['samples'][f'{name}/{cohort}']=row
                        print(seed,name,cohort,len(e),[(m,s[m]['complete_nonempty'],s[m]['selected']) for m in MODES],flush=True)
                    (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('ref','families','train_capture','capture','online','out'):p.add_argument(k,type=Path)
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--updates',type=int,default=900);p.add_argument('--repeats',type=int,default=8)
    phase(p.parse_args())
