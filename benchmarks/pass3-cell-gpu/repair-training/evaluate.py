"""Measure the six offline-trained Rust policies with the same resident CPU neural source forest."""
import argparse
from collections import Counter
from pathlib import Path
import json
from statistics import median
import numpy as np
import torch
from harness import Session,paths,read,EMPTY,verify
from train import load,reserved,edit

def decide(w,rows):
    if not rows:return np.empty((0,2),bool)
    x=torch.tensor([r['x'] for r in rows],dtype=torch.float32)
    hidden=torch.nn.functional.linear(x,torch.tensor(w['first']),torch.tensor(w['bias'])).relu()
    out=torch.nn.functional.linear(hidden,torch.tensor(w['last']),torch.tensor(w['offset']))
    return (out>0).numpy()

def score(rows,choices):
    y=np.array([[r['fast'],r['external']] for r in rows],dtype=bool).reshape(-1,2)
    weight=np.array([r['weight'] for r in rows])
    fast,leave=choices.T;legal,outer=y.T
    good=fast&legal&(~outer|leave)
    return dict(candidates=len(rows),actual_external=int(outer.sum()),wrong_omitted_external=int((~leave&outer).sum()),
                falsely_retained_external=int((leave&~outer).sum()),raw_fast=int(fast.sum()),unsafe_fast=int((fast&~legal).sum()),
                correct_boundary=int((leave==outer).sum()),correct_local_action=int((fast==legal).sum()),
                eligible=int(legal.sum()),verified=int(good.sum()),eligible_weight=int(weight[legal].sum()),verified_weight=int(weight[good].sum()))

def common_metrics(rows,weights,cutoff,union_log):
    h={};depth=[]
    for _,hi,lo in union_log:
        new=max(h.pop(hi,0)+1,h.get(lo,0))
        h[lo]=new;depth.append(new)
    pred=decide(weights,rows)
    strata={'all':lambda r:True,'rare_cost':lambda r:r['uses']*r['weight']>=cutoff,
            'short_union_history':lambda r:depth[r['union']]==1,
            'long_union_history':lambda r:depth[r['union']]>1,
            'held_template_family':lambda r:reserved(r['family']),
            'seen_template_partition':lambda r:not reserved(r['family'])}
    result={}
    for k,f in strata.items():
        mask=np.array([f(r) for r in rows]);result[k]=score([r for r,yes in zip(rows,mask) if yes],pred[mask])
    for kind in ('reader','collision','prior'):
        left=[];right=[]
        for r in rows:
            if kind!='reader' and not r['fast']:continue
            other=edit(r,kind)
            if other is None:continue
            left.append(r);right.append(other)
        a=decide(weights,left);b=decide(weights,right)
        col=1 if kind=='reader' else 0
        expected_a=np.array([r['external' if col else 'fast'] for r in left])
        expected_b=np.array([r['external' if col else 'fast'] for r in right])
        assert np.all(expected_a!=expected_b)
        result['toggle_'+kind]=dict(pairs=len(left),feature_identical=sum(a['x']==b['x'] for a,b in zip(left,right)),
                                    flipped=int((a[:,col]!=b[:,col]).sum()),
                                    both_correct=int(((a[:,col]==expected_a)&(b[:,col]==expected_b)).sum()))
    return result,pred

def execute(a):
    torch.set_num_threads(1)
    training=read(a.weights/'manifest.json');tables=training['bake']['tables']
    weights={k:read(a.weights/(k+'.json')) for k in training['styles']}
    arms=['generic','every','gate','real-1703'] if a.gate else ['generic','every','oracle',*weights]
    report={}
    a.out.mkdir(parents=True,exist_ok=False)
    for n in a.cases:
        program,image,gold,ob=paths(a.corpus,a.ref,n);rows=load(a.capture,n)
        for row in rows:row['x'][9]=float(row['table_name'] in tables)
        source=read(ob/'events.json')
        expected=[e for r in source for e in r if e[0]=='union']
        s=Session(a.binary,program,image,a.forest,a.out/n)
        summary={};timed={k:[] for k in arms};native_ms={k:[] for k in arms}
        try:
            recipients=neural=state_sha=None
            controls=[] if a.gate else ['unsafe','stale']
            for key in [*arms,*controls]:
                w=weights.get(key,EMPTY);mode='model' if key in weights else key
                actual=s.run(mode,w,tables,True);verify(actual,gold,expected)
                delivery=[v[:4] for v in actual['trial']['delivered']]
                if recipients is None:recipients=delivery;neural=actual['forest'];state_sha=actual['state_sha']
                assert recipients==delivery and neural==actual['forest'] and state_sha==actual['state_sha'],(key,n)
                stats=actual['trial']['counts']
                assert stats['applied']==sum(x[4] for x in actual['trial']['delivered'])
                allcounts=Counter(u[0] for u in recipients)
                summary[key]=dict(counts=stats,all_recipients=len(delivery),unions_with_subscribers=len(allcounts),
                    exact_deliveries=True,repair_key_probes=actual['repair_key_probes'],candidate_checks=actual['candidate_checks'],
                    fact_decodes=actual['fact_decodes'],port_decodes=actual['port_decodes'],runs=actual['runs'],unions=actual['unions'],
                    state_sha=state_sha,neural_rhs=len(neural['children']),total_rhs=neural['rhs'])
                if key in weights:
                    metrics,pred=common_metrics(rows,w,training['risk90'],expected)
                    shadow=s.run('shadow',w,tables,True);verify(shadow,gold,expected)
                    np.testing.assert_array_equal(np.array(shadow['trial']['decisions']),pred)
                    summary[key].update(common=metrics,rust_torch_shadow_decisions_equal=True)
            for rep in range(2*len(arms)):
                order=arms[rep%len(arms):]+arms[:rep%len(arms)]
                for key in order if rep<len(arms) else order[::-1]:
                    mode='model' if key in weights else key
                    actual=s.run(mode,weights.get(key,EMPTY),tables,False)
                    assert actual['forest']==neural and actual['state_sha']==state_sha and actual['runs']==summary[key]['runs']
                    timed[key].append(actual['whole_ms']);native_ms[key].append(actual['ms'])
            for key in arms:
                summary[key].update(whole_ms=timed[key],native_ms=native_ms[key],
                                    median_whole_ms=median(timed[key]),median_native_ms=median(native_ms[key]))
        finally:s.close()
        report[n]=summary
        (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
        print(n,[(k,summary[k]['counts']['applied'],summary[k]['repair_key_probes'],round(summary[k]['median_whole_ms'],2))
                 for k in arms],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','forest','capture','weights','binary','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax','histogram-scatter','gated-state'])
    p.add_argument('--gate',action='store_true')
    execute(p.parse_args())
