"""Rust CPU recurrent inference and Rust CPU validation, with two certificates per original source Run."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
from time import perf_counter_ns

import numpy as np
import torch
from export import compile_plan,read
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('unit_policy',HERE/'model.py')
impl=importlib.util.module_from_spec(spec);spec.loader.exec_module(impl)


def run(runtime,program,folder,policy=None,kind=None,observe=False,audit=False,residual=True,corrupt=False):
    args=[str(runtime),'--program',str(program),'--output',str(folder)]
    if policy:args+=['--action-policy',str(policy),'--action-kind',kind]
    if observe:args+=['--action-observe']
    if audit:args+=['--audit-events']
    if not residual:args+=['--actions-only']
    if corrupt:args+=['--action-bad-witness']
    start=perf_counter_ns();proc=subprocess.run(args,capture_output=True,text=True);end=perf_counter_ns()
    if proc.returncode:raise RuntimeError(proc.stderr[-8192:])
    return (end-start)/1e6


def semantic(folder,base):
    for k in ('state','rhs','writes','resumes','events'):
        assert read(folder/f'{k}.json')==read(base/f'{k}.json'),(folder,k)
    def steps(f):
        return [[s[k] for k in ('ordinal','ruleset','path','iterations','epoch','executed_bindings','changed')] for s in read(f/'report.json')['steps']]
    assert steps(folder)==steps(base)


def summarize(report,model_plan,rule_inputs):
    a=report['action_units'];events=a['issued'];kind=a['kind'].lower()
    used=set();parent=set();extra=set();dupes=set();duplicates=0
    proposed=multi=completed=wire=long_roots=long_hits=0
    example=None
    by_id={j[0]:j for j in model_plan['joins']}
    roots_expected={}
    for i,record in enumerate(events):
        r,row,leaf,code,address,rank,root,child,child_epoch,root_verified,child_verified=record
        rid=model_plan['entries'][leaf][0];width=len(rule_inputs[rid]['inputs'])
        key=(r,row);assert key not in roots_expected
        roots_expected[key]=(leaf,address)
        if (r,leaf,address) in dupes:duplicates+=1
        dupes.add((r,leaf,address))
        if kind=='raw':assert code==rid;wire+=8+8+8*width
        elif code<32:assert code==leaf;wire+=8
        else:
            assert kind=='macro' and by_id[code][1]==leaf;multi+=1;wire+=8
        if len(rule_inputs[rid]['q'])>1:long_roots+=1;long_hits+=int(root>0)
        if root:
            assert root not in used and root_verified;used.add(root);parent.add(root)
        if child:
            assert kind=='macro' and code>=32 and root and child>root and child not in used and child_epoch>r and child_verified
            used.add(child);extra.add(child);completed+=1
            if example is None:example=dict(issuance_run=r,row=row,compiled_unit=code,anchor=address,root_rule=rid,
                root_rhs=root,child_rule=model_plan['entries'][by_id[code][3]][0],parent_effect=by_id[code][2],child_run=child_epoch,child_rhs=child)
    total=sum(row['executed_bindings'] for row in report['steps']);assert total==a['rhs']
    assert len(a['provenance'])==len(extra)
    if not a['residual']:assert len(used)==total
    counts=dict(runs=a['source_runs'],emission_slots=a['source_runs']*2,active_certificates=len(events),
                root_winners=len(parent),child_winners=len(extra),neural_rhs=len(used),exact_residual=total-len(used),source_rhs=total,
                offered_macros=multi,two_rhs_from_one_certificate=completed,zero_rhs=len(events)-len(parent),
                one_rhs=len(parent)-len(extra),duplicates=duplicates,wire_bytes=wire,
                two_atom_root_proposals=long_roots,two_atom_root_winners=long_hits,
                raw_fields=a['explicit_fields'],raw_rejections=a['raw_rejections'],root_verifier_attempts=a['root_attempts'],
                child_verifier_attempts=a['child_attempts'],verifier_point_reads=a['point_reads'],
                candidate_scores=a['actions_scored'],example=example)
    return counts,roots_expected


def parity(report,plan,checkpoint):
    net=impl.Actor(plan['joins'])
    net.load_state_dict(torch.load(checkpoint,weights_only=True));net.eval()
    for j,(_,_,_,right) in enumerate(plan['joins']):
        if plan['entries'][right][0]<0:net.unit_bias.data[j]=-1e6
    previous=torch.zeros(1,2,12);maximum=0;decision={(e[0],e[1]):e for e in report['action_units']['issued']}
    with torch.inference_mode():
        for run,(stage,records,actual) in enumerate(report['action_units']['observations'],1):
            x=torch.zeros(1,256,8);x[:,:,0]=-1;x[:,:,1]=stage
            if records:
                t=torch.tensor(records);idx=t[:,0]
                x[0,idx,0]=t[:,1].float();x[0,idx,2:]=t[:,2:].float()
            _,_,_,previous,chosen=net.step(x,previous)
            expected=torch.tensor(actual)
            np.testing.assert_array_equal(previous[0,:,8:],expected[:,8:])
            maximum=max(maximum,float((previous[0,:,:8]-expected[:,:8]).abs().max()))
            for row in range(2):
                sample=decision.get((run,row));assert bool(sample)==bool(previous[0,row,-1])
                if sample:
                    idx=int(chosen[0,row]);assert sample[3]==(plan['joins'][idx][0] if idx>=0 else int(previous[0,row,8])-1)
    assert maximum<.002,maximum
    return dict(runs=len(report['action_units']['observations']),discrete_differences=0,max_latent_difference=maximum)


def study(a):
    torch.set_num_threads(1);a.out.mkdir(parents=True,exist_ok=False);summary={}
    donor=a.ref/'sum-bits/program.json'
    for case in a.cases:
        anchor=case in ('sum-bits','dot-product')
        program=a.ref/case/'program.json' if anchor else a.corpus/case/'program.json'
        im=a.ref/f'release-input-{case}' if anchor else a.corpus/case/'input'
        original=a.ref/f'events-{case}' if anchor else a.corpus/case/'observation'
        rule_inputs=read(im/'ingress.json')['rules']
        base=a.out/f'{case}-reference'
        run(a.runtime,program,base,audit=True)
        for k in ('state','rhs','writes','resumes'):assert read(base/f'{k}.json')==read(original/f'{k}.json'),(case,k)
        for seed in a.seeds:
            train=a.model/f'train-{seed}'
            plan=compile_plan(program,im,donor,train/'model.json')
            packet=a.out/f'{case}-{seed}-plan.json';packet.write_text(json.dumps(plan,separators=(',',':')))
            result={};same=None
            for kind in ('raw','leaf','macro','bad-witness','raw-only','leaf-only','macro-only'):
                residual=not kind.endswith('-only')
                actual='raw' if kind=='bad-witness' else kind.split('-')[0]
                folder=a.out/f'{case}-{seed}-{kind}'
                run(a.runtime,program,folder,packet,actual,observe=kind in ('macro','raw'),audit=True,residual=residual,corrupt=kind=='bad-witness')
                if residual:semantic(folder,base)
                report=read(folder/'report.json');counts,decisions=summarize(report,plan,rule_inputs)
                if residual:
                    if same is None:same=decisions
                    else:assert same==decisions,(case,seed,kind)
                else:
                    first=next((i for i,(s,v) in enumerate(zip(report['steps'],read(base/'report.json')['steps']),1)
                                if any(s[k]!=v[k] for k in ('ruleset','executed_bindings','changed'))),None)
                    counts['first_divergence']=first
                if kind=='macro':counts['independent_pytorch_rollout']=parity(report,plan,train/'actor.pt')
                counts['aligned']=residual;result[kind]=counts
            arms=['exact','raw','leaf','macro'];result['exact']={'aligned':True}
            for arm in arms:result[arm].update(inference_ms=[],cli_ms=[])
            for t in range(2*len(arms)):
                order=arms[t%4:]+arms[:t%4]
                for arm in order if t<len(arms) else order[::-1]:
                    folder=a.out/f'{case}-{seed}-{arm}-timed-{t}'
                    ms=run(a.runtime,program,folder,packet if arm!='exact' else None,arm)
                    prof=read(folder/'report.json')
                    assert read(folder/'state.json')==read(base/'state.json')
                    if arm!='exact':
                        measured,_=summarize(prof,plan,rule_inputs)
                        assert measured['neural_rhs']==result[arm]['neural_rhs'] and measured['child_winners']==result[arm]['child_winners']
                    result[arm]['cli_ms'].append(ms);result[arm]['inference_ms'].append(1000*prof['inference_seconds'])
            for arm in arms:result[arm]['median_ms']=median(result[arm]['inference_ms']);result[arm]['median_cli_ms']=median(result[arm]['cli_ms'])
            summary[f'{case}/{seed}']=result
            (a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
            print(case,seed,[(arm,result[arm].get('neural_rhs'),result[arm].get('child_winners'),round(result[arm]['median_ms'])) for arm in arms],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','model','runtime','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    study(p.parse_args())
