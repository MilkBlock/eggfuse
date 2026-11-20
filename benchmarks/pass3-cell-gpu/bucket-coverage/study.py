"""Table-key and versioned page closures on real, identical recurrent neural proposals."""
import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from smoke import HERE,inputs,load_catalog,read,specialize,validate,verify
from feedback_study import bind_session


class PhaseStamp:
    """A synchronized host wall-clock boundary used only in the timing diagnostic."""
    def record(self):
        torch.mps.synchronize()
        self.time=perf_counter_ns()


def risk_oracle(src):
    with np.load(src/'output.npz') as g,np.load(src/'neural-inputs.npz') as a:
        truth={(int(t[0]),int(t[1]),int(p)-1,int(t[3])) for t,p in zip(g['rhs'],a['pivot']) if p}
    return truth


def report(folder,entries,truth,control):
    with np.load(folder/'neural-output.npz') as z:
        raw=z['raw'].copy();verdict=z['verdict'].copy();neural=z['rhs_ordinal'].copy()
    won=validate(folder,entries)
    with np.load(folder/'buckets.npz') as z:
        log=z['log'];bank=z['bank'];counters=z['stats'];space=int(z['meta_bytes'])
    with np.load(folder/'output.npz') as z:
        rhs=z['rhs'];source_runs=len(z['runs'])
    code=log[:,:,4];in_scope=code!=0;claimed=int(in_scope.sum());good=(code==2)|(code==3)
    omitted=0;union_stale=0;siblings=[]
    for t,slot in zip(*np.where(code==5)):
        l=int(log[t,slot,0])-1;rid,pivot,*_=entries[l]
        omitted+=int((t+1,rid,pivot,int(log[t,slot,7])-1) in truth)
    for t,slot in zip(*np.where(code==4)):
        x=log[t,slot];assert x[15]<x[2] and x[7]<x[3];union_stale+=1
    for t,col in zip(*np.where(bank[:,:,4]>0)):
        rid,piv,seed,pos,ord_=map(int,bank[t,col])
        witness=rhs[ord_-1]
        assert (int(witness[0]),int(witness[1]),int(witness[3]))==(t+1,rid,seed)
        siblings.append(ord_)
    all_ord=[int(v) for v in neural[neural>0]]+siblings
    assert len(set(all_ord))==len(all_ord)
    assert np.all(log[:,:,14][~good]==0)
    if good.any():assert int(good.sum())==int(counters[1])
    roles=read(folder/'run.json')['execution_roles'];assert roles['rhs_inputs_from_bucket_enumeration']==len(siblings)
    assert roles['rhs_inputs_from_exact_search']+won+len(siblings)==len(rhs)
    buckets={}
    for t,slot in zip(*np.where(good)):
        x=log[t,slot];key=(int(t),int(x[0]),int(x[7]))
        extent,pages=buckets.setdefault(key,(int(x[5]),{}))
        assert extent==int(x[5])
        pages[int(x[15])]=int(x[6])
    covered_keys=sum(sum(pages.values())==extent for extent,pages in buckets.values())
    distinct_remainder=sum(extent-sum(pages.values()) for extent,pages in buckets.values())
    partial=good&(log[:,:,6]<log[:,:,5])
    stats=dict(runs=source_runs,rhs=len(rhs),neural_committed=won,bucket_committed=len(siblings),
        residual_committed=len(rhs)-len(all_ord),raw=int((verdict[:,:,0]>0).sum()),tasks=claimed,
        distinct_checked_keys=len(buckets),distinct_whole_keys_closed=covered_keys,
        distinct_retained_rows=distinct_remainder,verified_pages=int(good.sum()),full_key_claims=int((good & ~partial).sum()),partial_page_claims=int(partial.sum()),
        distinct_source_rows_closed=int(log[:,:,14].sum()),repeated_accepted_claims=int((good&(log[:,:,14]==0)).sum()),
        outside_verified_range=int((log[:,:,5][partial]-log[:,:,6][partial]).sum()),
        multirow_bucket_claims=int((good&(log[:,:,5]>1)).sum()),largest_observed_bucket=int(log[:,:,5].max()),
        page_witness_rows=int(log[:,:,6].sum()),directory_build_visits=int(log[:,:,9].sum()),
        directory_enumeration_visits=int(log[:,:,10].sum()),independent_witness_visits=int(log[:,:,11].sum()),
        unique_index_visits=int(log[:,:,12].sum()),unproposed_sibling_checks=int(log[:,:,13].sum()),
        accepted_extra_siblings=int(log[:,:,8].sum()),residual_seed_checks_skipped=int(counters[0]),
        rejected_missing=int((code==5).sum()),omitted_reference_winners=omitted,rejected_stale_after_union=union_stale,
        no_authorized_closure=int((code==1).sum()),hidden_or_unresolved=int((code==6).sum()),verified_extent_audits=int(counters[1]),
        false_closures=0,allocated_study_bytes=space,route=read(folder/'run.json')['neural_work_counts'])
    return stats,raw,verdict


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    complete={}
    for case in a.cases:
        image,prog,gold=inputs(a.corpus,a.ref,case);entries=load_catalog(image,prog,a.ref/'sum-bits/program.json')
        truth=risk_oracle(a.capture/case)
        with np.load(gold/'output.npz') as z:baseline={k:z[k] for k in ('runs','resumes','writes','rhs')}
        for seed in a.seeds:
            weights=read(HERE.parent/f'recurrent-generator/receipts/actor-{seed}-2.json')
            cfg=dict(catalog=entries,weights=weights['weights'],ranks=8,rows=2,hidden=8,waves=2,
                     feedback=2,receipt_head=True,close=False)
            panels=[(p,m,'intact') for p in ('unique','partial') for m in ('positive','unique','range')]
            if seed==1703:panels.extend(('partial','range',c) for c in ('omit','stale','duplicate','null'))
            out={};sessions={}
            raw_reference=None
            for panel,mode,ctrl in panels:
                label=f'{panel}-{mode}-{ctrl}'
                fn=specialize(image,entries,panel,mode,ctrl if ctrl!='null' else 'intact')
                localcfg=dict(cfg,intervention=3 if ctrl=='null' else 0)
                folder=a.out/f'{case}-{seed}-{label}'
                fn(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,neural=localcfg,count_work=True)
                verify(folder,gold,image)
                out[label],raw,verdict=report(folder,entries,truth,ctrl)
                if raw_reference is None:
                    raw_reference=raw;verdict_reference=verdict
                elif ctrl!='null':
                    np.testing.assert_array_equal(raw,raw_reference)
                    np.testing.assert_array_equal(verdict,verdict_reference)
                else:assert out[label]['neural_committed']==out[label]['tasks']==0
                if ctrl!='intact':continue
                folder=a.out/f'{case}-{seed}-{label}-resident'
                fn(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,neural=cfg,
                   measure_resident=bind_session(sessions,label))
                verify(folder,gold,image)
                out[label]['ms']=[]
            labels=list(sessions)
            for i in range(a.reps):
                order=labels[i%len(labels):]+labels[:i%len(labels)]
                for label in order if i%2==0 else order[::-1]:
                    reset,infer,buf=sessions[label];reset();torch.mps.synchronize()
                    start=perf_counter_ns();infer();torch.mps.synchronize();out[label]['ms'].append((perf_counter_ns()-start)/1e6)
                    s=buf['state'].cpu().tolist();assert s[7] and not s[5]
                    for k,pos in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                        got=buf[k][:s[pos]].cpu().numpy();want=baseline[k]
                        if k=='rhs':
                            np.testing.assert_array_equal(got[:,:2],want[:,:2]);got,want=got[:,4:],want[:,4:]
                        np.testing.assert_array_equal(got,want)
                    np.testing.assert_array_equal(buf['raw_trace'][:s[11]].cpu().numpy(),raw_reference)
            for label in labels:out[label]['median_ms']=median(out[label]['ms'])
            if seed==1703:
                # Instrument selected active invocations on a separate pass. The synchronized
                # wall intervals include dispatch/fencing; the primary timings above do not.
                for panel,mode in [('unique','positive'),('unique','unique'),('partial','range')]:
                    base=f'{panel}-{mode}-intact'
                    selected={}
                    for t,wave in zip(*np.nonzero((raw_reference[:,:,-1].reshape(len(raw_reference),2,2)>0).sum(2))):
                        if len(selected)>=24:break
                        selected[int(t),int(wave)]=int(raw_reference[t,2*wave:2*wave+2,-1].sum())
                    for t in list(dict.fromkeys(x[0] for x in selected)):selected[t,2]=int(raw_reference[t,:,-1].sum())
                    stamps={k:(PhaseStamp(),PhaseStamp()) for k in selected}
                    fn=specialize(image,entries,panel,mode,clock=stamps)
                    folder=a.out/f'{case}-{seed}-{base}-kernel-timing'
                    fn(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,neural=cfg)
                    verify(folder,gold,image)
                    samples=[dict(run=t+1,wave=w,proposals=n,us=(stamps[t,w][1].time-stamps[t,w][0].time)/1000) for (t,w),n in selected.items()]
                    out[base]['synchronized_intervals']=samples
            complete[f'{case}/{seed}']=out
            (a.out/'results.json').write_text(json.dumps(complete,indent=1)+'\n')
            print(case,seed,[(k,round(out[k]['median_ms']),out[k]['distinct_source_rows_closed'],out[k]['bucket_committed']) for k in labels],flush=True)
            sessions.clear()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709]);p.add_argument('--reps',type=int,default=6)
    with torch.inference_mode():run(p.parse_args())
