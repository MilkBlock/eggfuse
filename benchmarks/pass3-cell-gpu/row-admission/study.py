"""Fixed proposal-slot budget, native recurrent rows and verified cross-Run Cell macros."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns
import subprocess

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'action-granularity'))
from export import compile_plan,read


def launch(binary,program,out,plan=None,*,audit=False,residual=True):
    cmd=[binary,'--program',program,'--output',out]
    if plan:cmd.extend(['--action-policy',plan,'--action-kind','macro'])
    if audit:cmd.append('--audit-events')
    if not residual:cmd.append('--actions-only')
    start=perf_counter_ns()
    done=subprocess.run(cmd,capture_output=True,text=True)
    if done.returncode:raise RuntimeError(done.stderr)
    return (perf_counter_ns()-start)/1e6


def check_graph(out,base):
    for k in ('state','rhs','resumes','writes','events'):
        assert read(out/f'{k}.json')==read(base/f'{k}.json'),(k,out)
    return counts(out)==counts(base)


def counts(out):
    return [(s['ruleset'],s['epoch'],s['changed'],s['executed_bindings']) for s in read(out/'report.json')['steps']]


def metrics(out,rows,waves,mode):
    doc=read(out/'report.json');a=doc['action_units'];steps=doc['steps']
    by_epoch={s['epoch']:i for i,s in enumerate(steps)}
    slots=rows*waves;by_slot=Counter();per_row=[0]*rows;closed=Counter();used=set();actions=set()
    unique=set();dupes=Counter();first=defaultdict(set);won_task=set()
    for event in a['issued']:
        epoch,slot,leaf,unit,addr,_,root,child,child_epoch,root_ok,child_ok=event
        key=(epoch,leaf,addr);r=slot%rows;by_slot[epoch,r]+=1
        if key in unique:dupes['same_task']+=1
        unique.add(key)
        if slot//rows==0:first[epoch].add(r)
        owner=(addr*0x9e3779b1+leaf*0x85ebca77)%rows
        if mode=='static':assert owner==r
        if root:
            assert root_ok and root not in used;used.add(root);closed[epoch]+=1;per_row[r]+=1
            won_task.add(key)
        if child:
            assert child_ok and child not in used and root<child and child_epoch>epoch
            used.add(child);closed[child_epoch]+=1;per_row[r]+=1
        actions.add((epoch,slot,leaf,addr))
    transfers=0;transfer_hits=0
    for epoch,wave,original,taker,leaf,addr,version,source in a['handoffs']:
        assert original==(addr*0x9e3779b1+leaf*0x85ebca77)%rows and original!=taker
        assert version<=epoch and (epoch,wave*rows+taker,leaf,addr) in actions
        transfer_hits+=int((epoch,leaf,addr) in won_task);transfers+=1
    if mode!='transfer':assert not transfers
    if mode in ('static','transfer'):assert not dupes['same_task']
    total=sum(s['executed_bindings'] for s in steps)
    assert len(a['issued'])+a['idle_slots']==len(steps)*slots and total==a['rhs']
    full=sum(s['executed_bindings']>0 and s['executed_bindings']==closed[s['epoch']] for s in steps)
    return dict(runs=len(steps),rhs=total,slots=len(steps)*slots,issued=len(a['issued']),idle=a['idle_slots'],
                duplicates=dupes['same_task'],roots=len(won_task),children=len(used)-len(won_task),
                neural=len(used),exact=total-len(used),by_row=per_row,nonempty=sum(s['executed_bindings']>0 for s in steps),
                fully_neural_nonempty=full,scored=a['actions_scored'],transfer_scored=a['handoff_scores'],
                transfers=transfers,transfer_root_wins=transfer_hits,point_reads=a['point_reads'],
                tasks=unique,winners=won_task,first=first)


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    donor=a.ref/'sum-bits/program.json'
    for name in a.cases:
        anchor=name in ('sum-bits','dot-product')
        program=a.ref/name/'program.json' if anchor else a.corpus/name/'program.json'
        image=a.ref/f'release-input-{name}' if anchor else a.corpus/name/'input'
        base=a.out/f'{name}-exact'
        launch(a.binary,program,base,audit=True)
        source=a.ref/f'events-{name}' if anchor else a.corpus/name/'observation'
        for k in ('rhs','resumes','state','writes'):assert read(base/f'{k}.json')==read(source/f'{k}.json')
        for seed in a.seeds:
            summary={};issued={};winners={};first_wave={};plans={}
            compiled=compile_plan(program,image,donor,a.models/f'model-{seed}.json')
            for rows in (1,2,4):
                waves=8//rows
                for mode in ('free','free_once','static','transfer'):
                    arm=f'{rows}x{waves}-{mode}'
                    plan=a.out/f'{name}-{seed}-{arm}.json'
                    plan.write_text(json.dumps(dict(compiled,schedule=dict(rows=rows,waves=waves,admission=mode))))
                    dest=a.out/f'{name}-{seed}-{arm}'
                    launch(a.binary,program,dest,plan,audit=True)
                    assert check_graph(dest,base)
                    item=metrics(dest,rows,waves,mode)
                    issued[arm]=item.pop('tasks');winners[arm]=item.pop('winners');first_wave[arm]=item.pop('first')
                    item['ms']=[];item['cli_ms']=[];item['aligned']=True
                    summary[arm]=item;plans[arm]=plan
            # Never use future labels during inference. A root won in any matched arm
            # is an independently realized opportunity, a lower bound on all opportunities.
            observed=set.union(*winners.values())
            for arm,item in summary.items():
                rows=int(arm[0]);missing=observed-issued[arm]
                item['known_root_opportunities']=len(observed)
                item['missed_known_root_opportunities']=len(missing)
                item['first_idle_run_with_known_omission']=min((e for e,_,_ in missing if len(first_wave[arm][e])<rows),default=None)
            exact=[];order=['exact',*summary]
            for trial in range(6):
                rotated=order[(trial*5)%len(order):]+order[:(trial*5)%len(order)]
                for arm in rotated if trial%2==0 else rotated[::-1]:
                    dest=a.out/f'{name}-{seed}-{arm}-timed-{trial}'
                    ms=launch(a.binary,program,dest,plans.get(arm))
                    doc=read(dest/'report.json')
                    assert read(dest/'state.json')==read(base/'state.json')
                    elapsed=1000*doc['inference_seconds']
                    if arm=='exact':exact.append(elapsed);continue
                    events=doc['action_units']['issued']
                    assert sum((e[6]>0)+(e[7]>0) for e in events)==summary[arm]['neural']
                    summary[arm]['ms'].append(elapsed);summary[arm]['cli_ms'].append(ms)
            for v in summary.values():v['median_ms']=median(v['ms'])
            # One no-residual run for each distinct admission strategy on the primary shape.
            for mode in ('free','free_once','static','transfer'):
                arm='2x4-'+mode;dest=a.out/f'{name}-{seed}-{arm}-only'
                launch(a.binary,program,dest,plans[arm],residual=False)
                v=metrics(dest,2,4,mode);assert v['exact']==0
                one,truth=counts(dest),counts(base)
                first=next((i for i,(o,g) in enumerate(zip(one,truth),1) if o!=g),None)
                summary[arm]['without_residual']=dict(runs=len(one),rhs=v['rhs'],first_divergence=first)
            summary['exact']=dict(ms=exact,median_ms=median(exact))
            results[f'{name}/{seed}']=summary
            (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            print(name,seed,[(k,v['roots'],v['children'],v['transfers']) for k,v in summary.items() if k.startswith('2x4')],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','binary','models','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',nargs='+',type=int,default=[1703,1709])
    study(p.parse_args())
