"""Train a late-bound child proposal gate offline, execute only neural-root transitions online on native Graph."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch
from torch import nn

from compile import plan
ACTION=Path(__file__).resolve().parent.parent/'action-granularity'
sys.path.insert(0,str(ACTION))
from export import compile_plan


def read(p):return json.loads(p.read_bytes())
def save(p,x):p.write_text(json.dumps(x,separators=(',',':'))+'\n')
def run(a,program,dest,config=None,action=None,audit=True):
    args=[str(a.runtime),'--program',str(program),'--output',str(dest)]
    if config:args+=['--late-merge-model',str(config)]
    if action:args+=['--action-policy',str(action),'--action-kind','leaf']
    if audit:args+=['--audit-events']
    start=perf_counter_ns();p=subprocess.run(args,capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stderr[-8192:])
    return (perf_counter_ns()-start)/1e6
def cfg(program,weights,mode='neural',relax=True,corrupt=False,only=False):
    return dict(digest=hashlib.sha256(program.read_bytes()).hexdigest(),routes=plan(program),weights=weights,mode=mode,relax=relax,only_consumer=only,corrupt=corrupt)

def fit(a):
    a.out.mkdir(parents=True,exist_ok=False)
    features=[];labels=[];counts={}
    for n,case in read(a.corpus/'collection.json').items():
        if case['split']!='train':continue
        p=a.corpus/n/'program.json';config=a.out/f'{n}.json';save(config,cfg(p,[0.]*7,'observe'))
        dest=a.out/n;run(a,p,dest,config)
        gold=a.corpus/n/'observation'
        for k in ('rhs','resumes','writes','state'):assert read(dest/f'{k}.json')==read(gold/f'{k}.json'),k
        records=read(dest/'report.json')['late_merge_ports']['records']
        features.extend(r['features'] for r in records);labels.extend(bool(r['resolved']) for r in records)
        counts[n]=dict(candidates=len(records),committed=sum(bool(r['resolved']) for r in records))
    assert len(counts)==4 and any(labels) and not all(labels)
    x=torch.tensor(features);y=torch.tensor(labels,dtype=torch.float32);torch.set_num_threads(1)
    for seed in (1703,1709):
        torch.manual_seed(seed);model=nn.Linear(6,1);opt=torch.optim.Adam(model.parameters(),lr=.03)
        for _ in range(400):
            logits=model(x)[:,0];loss=nn.functional.binary_cross_entropy_with_logits(logits,y,pos_weight=torch.tensor(2.))
            opt.zero_grad();loss.backward();opt.step()
        w=model.weight.detach().flatten().tolist()+[model.bias.item()]
        save(a.out/f'gate-{seed}.json',dict(weights=w,seed=seed,train=counts,updates=400,threshold=0))
    print(counts,flush=True)


def metrics(r,roles,ids,consumer):
    events=r['late_merge_ports']['records'];parent_rid={q[0] for q in r['late_merge_ports']['routes']}
    roots={e[6]:i for i,e in enumerate(r['action_units']['issued']) if e[6]} if 'action_units' in r else {}
    won=set();selected=0;rebound=0;merged=0
    for e in events:
        if roles!='observe':
            assert e['root'] is not None and roots[e['source']]==e['root']
        assert e['rid'] in parent_rid
        if e['selected']:selected+=1
        if e['merged'] is not None:
            assert e['old'] is not None and e['out'] is not None and e['candidate_pair'] is not None;merged+=1
        if e['resolved']:
            assert e['resolved'] not in won and e['source']<e['resolved'] and e['run']<e['consumer_run']
            assert e['selected'] and e['merged'] is not None;won.add(e['resolved']);rebound+=e['union_revalidated']
            if ids is not None:assert ids[e['resolved']-1][2]==r['late_merge_ports']['routes'][e['route']][6]
    return dict(potential=len(events),emitted=selected,realized_merge_outputs=merged,child_rhs=len(won),
                revalidated_union_children=rebound,root_neural=len(roots),overlapping_ordinary=r['late_merge_ports']['extra_overlaps'],
                all_rhs=sum(s['executed_bindings'] for s in r['steps']),source_runs=len(r['steps']),
                residual_rhs=sum(s['executed_bindings'] for s in r['steps'])-len(won)-len(roots),
                example=next((e for e in events if e['resolved']),None))

def study(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    for n in a.cases:
        anchor=n in ('sum-bits','dot-product')
        program=a.ref/n/'program.json' if anchor else a.corpus/n/'program.json'
        image=a.ref/f'release-input-{n}' if anchor else a.corpus/n/'input'
        gold=a.ref/f'events-{n}' if anchor else a.corpus/n/'observation'
        donor=a.ref/'sum-bits/program.json'
        ids=read(a.references/f'v4-{n}'/'references.json')['lhs']
        base_reference=None
        for seed in a.seeds:
            model=read(a.gates/f'gate-{seed}.json');action=a.out/f'{n}-{seed}-action.json'
            save(action,compile_plan(program,image,donor,a.action/f'train-{seed}'/'model.json'))
            modes=[('no-extension','null',True,False,False),('learned','neural',True,False,False),('pinned','neural',False,False,False),
                   ('all-neural','all-neural',True,False,False),('wrong','neural',True,True,False),('no-consumer-residual','neural',True,False,True)]
            summary={};configs={}
            for label,mode,relax,corrupt,only in modes:
                config=a.out/f'{n}-{seed}-{label}.json';save(config,cfg(program,model['weights'],mode,relax,corrupt,only));configs[label]=config
                dest=a.out/f'{n}-{seed}-{label}';run(a,program,dest,config,action)
                r=read(dest/'report.json');consumer=read(config)['routes'][0][6]
                if not only:
                    for k in ('rhs','resumes','writes','state'):assert read(dest/f'{k}.json')==read(gold/f'{k}.json'),(n,label,k)
                    if base_reference is None:base_reference=read(dest/'events.json')
                    assert read(dest/'events.json')==base_reference
                summary[label]=metrics(r,mode,ids if not only else None,consumer)
                if only:
                    data=read(gold/'report.json')['steps']
                    summary[label]['first_divergence']=next((i for i,(s,v) in enumerate(zip(r['steps'],data),1)
                        if any(s[k]!=v[k] for k in ('ruleset','changed','executed_bindings'))),None)
                else:summary[label]['source_exact']=True
            assert summary['wrong']['child_rhs']==summary['no-extension']['child_rhs']==0
            order=['no-extension','learned','pinned','all-neural']
            for label in order:summary[label]['ms']=[]
            for trial in range(2*len(order)):
                seq=order[trial%len(order):]+order[:trial%len(order)]
                for label in seq if trial<len(order) else seq[::-1]:
                    dest=a.out/f'{n}-{seed}-{trial}-{label}'
                    run(a,program,dest,configs[label],action,False)
                    r=read(dest/'report.json');summary[label]['ms'].append(r['inference_seconds']*1000)
                    actual=metrics(r,'neural',ids,consumer);assert actual['child_rhs']==summary[label]['child_rhs']
                    assert read(dest/'state.json')==read(gold/'state.json')
            for label in order:summary[label]['median_ms']=median(summary[label]['ms'])
            result[f'{n}/{seed}']=summary;save(a.out/'results.json',result)
            print(n,seed,[(l,summary[l]['emitted'],summary[l]['child_rhs'],summary[l]['revalidated_union_children']) for l in order],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('runtime','corpus','ref','action','references','gates','out'):p.add_argument(k,type=Path)
    p.add_argument('--fit',action='store_true');p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709]);a=p.parse_args()
    if a.fit:fit(a)
    else:study(a)
