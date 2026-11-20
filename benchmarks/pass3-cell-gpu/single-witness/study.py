"""A learned native candidate fixes zero or one typed source before every dependent point check."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
import numpy as np
from capture import launch,aligned,paths,read,dump
from calibrate import prepare,rollout


def attribution(folder,gold_trace,source,model,captured):
    rep=read(folder/'report.json');t=rep['single_witness'];rows=t['committed'];ev=read(folder/'events.json')
    with np.load(gold_trace/'output.npz') as z:
        rhs=z['rhs'];run_offsets=np.cumsum(z['runs'][:,1])-z['runs'][:,1]
    assert len(rhs)==t['rhs']
    rules=read(source)['recipe']['rules']
    resumed=set();births={};writes={};history={}
    for run,events in enumerate(ev):
        for e in events:
            if e[0]=='resume':resumed.add(int(run_offsets[run])+e[1])
            elif e[0]=='birth':
                births[e[4]]=(run+1,None if e[5] is None else int(run_offsets[run])+e[5][0]+1)
            elif e[0]=='write':
                writes.setdefault(e[4],[]).append((run+1,None if e[2] is None else int(run_offsets[run])+e[2][0]+1))
    assert len(resumed)==sum(1 for run in ev for e in run if e[0]=='resume')
    protected=set(t.get('guarded_ordinals',[]));ids=set();ordinals=set();counts=Counter();examples={}
    for o,epoch,rid,pivot,w,version,initial,score,token_id,witnesses,*extra in rows:
        assert token_id not in ids and o not in ordinals and tuple(rhs[o-1,:2])==(epoch,rid)
        ids.add(token_id);ordinals.add(o)
        actual={i:addr for i,addr in witnesses}
        expected={i for i,atom in enumerate(rules[rid]['query']) if 'table' in atom['call']}
        assert set(actual)==expected
        if pivot is None: assert w is None
        else: assert actual[pivot]==w and version<=epoch
        if model is not None and o not in protected and not any(extra):assert score>=(t['floors'][rid] if 'floors' in t else model['threshold'])-1e-6
        source_kind='zero' if w is None else 'initial' if initial else 'runtime'
        counts[source_kind]+=1;counts['spine' if o in resumed else 'ordinary']+=1
        if w is not None and initial:counts['initial_updated' if version>0 else 'initial_epoch_zero']+=1
        if w is not None and not initial:
            if w[0]==1:parent=births.get((w[1]<<32)|w[2])
            else:parent=next((v for v in reversed(writes.get(w[1],[])) if v[0]<epoch),None)
            if parent is not None and parent[0]<epoch and parent[1] is not None:
                counts['known_earlier_writer']+=1
                assert parent[1]<o
                history[o]=parent[1]
        if source_kind not in examples:examples[source_kind]=dict(rhs=o,run=epoch,rule=rid,pivot=pivot,typed_root=w,version=version,token=token_id)
    for o,parent in history.items():counts['earlier_writer_also_neural' if parent in ordinals else 'earlier_writer_exact']+=1
    digest=hashlib.sha256(np.asarray(sorted(ordinals),dtype='<i8').tobytes()).hexdigest()
    return dict(ordinal_sha256=digest,ordinals=sorted(ordinals),all_unique_ids=True,counts=dict(counts),examples=examples)


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);reports={}
    for case in a.cases:
        program,gold=paths(a.corpus,a.ref,case);cp=a.captures/case
        canonical=read(gold/'report.json');total=sum(s['executed_bindings'] for s in canonical['steps'])
        traced=a.ref/f'release-{case}' if case in ('sum-bits','dot-product') else a.corpus/case/'device'
        for seed in a.seeds:
            record={};session_labels=[];files={}
            arms=['all','none','high','balanced','coverage','zero-state','only']
            for arm in arms:
                cfg=read(a.models/f'{seed}-{arm if arm in ("balanced","coverage") else "high"}.json')
                cfg['residual']=arm!='only'
                if arm in ('all','none'):cfg.update(mode=arm,model=None)
                if arm=='zero-state':cfg['mode']='zero-state'
                path=a.out/f'{case}-{seed}-{arm}.json';dump(path,cfg)
                dest=a.out/f'{case}-{seed}-{arm}';launch(a.build/'runtime',program,dest,path)
                report=read(dest/'report.json');stats=report['single_witness'];work=stats['work'];neural=len(stats['committed'])
                initial=dict(source_rhs=total,rhs=stats['rhs'],neural=neural,exact=stats['rhs']-neural,raw=work[1],
                             candidate_universe=work[0],checked=work[2],point_reads=work[3],primitives=work[4],
                             admitted=work[5],residual_valid=work[6],eligible=stats['rules'],runs=len(report['steps']),
                             mode=cfg['mode'],threshold=cfg['model']['threshold'] if cfg['model'] else None)
                if arm!='only':
                    aligned(dest,gold)
                    acheck=attribution(dest,traced,program,cfg['model'],cp)
                    initial.update(source_aligned=True,provenance=acheck)
                    if arm in ('high','balanced','coverage'):
                        m=cfg['model'];parity=rollout(prepare(cp/'report.json',m),m,m['threshold'])
                        assert parity['total']==work[0] and parity['emitted']==work[1] and parity['hits']==work[5],(case,seed,arm,parity,work)
                        initial['independent_decisions']=parity
                        assert work[1]<work[0] and neural>0
                else:
                    assert stats['rhs']==neural
                    trace,base=read(dest/'rhs.json'),read(gold/'rhs.json')
                    first=next((i+1 for i,(x,y) in enumerate(zip(trace,base)) if x!=y),None)
                    assert first is not None
                    initial['first_divergence']=first
                record[arm]=initial
                if arm in ('all','high','balanced'):
                    files[arm]=str(path);session_labels.append(arm)
            files['exact']='exact';session_labels.append('exact');record['exact']={}
            proc=subprocess.Popen([str(a.build/'session'),str(program)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            try:
                assert proc.stdout.readline().strip()=='ready';digest=None
                for trial in range(2*len(session_labels)):
                    order=session_labels[trial%4:]+session_labels[:trial%4]
                    for arm in order if trial<4 else order[::-1]:
                        proc.stdin.write(files[arm]+'\n');proc.stdin.flush();z=json.loads(proc.stdout.readline())
                        if digest is None:digest=z['graph']
                        assert z['graph']==digest and (arm=='exact' or z['single']==record[arm]['neural'])
                        record[arm].setdefault('samples_ms',[]).append(z['ms'])
                proc.stdin.write('stop\n');proc.stdin.flush();assert proc.wait()==0
            finally:
                if proc.poll() is None:proc.kill();proc.wait()
            for arm in session_labels:record[arm]['median_ms']=median(record[arm]['samples_ms'])
            reports[f'{case}/{seed}']=record
            (a.out/'results.json').write_text(json.dumps(reports,separators=(',',':'))+'\n')
            print(case,seed,[(k,record[k]['neural'],record[k]['raw'],record[k]['candidate_universe']) for k in ('all','high','balanced','coverage')],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','build','models','captures','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    run(p.parse_args())
