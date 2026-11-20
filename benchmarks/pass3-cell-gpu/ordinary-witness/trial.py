"""Measure, then independently audit each candidate-path RHS on the whole native source schedule."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
from statistics import median
import numpy as np
from plan import compile_program,sealed_plans

def read(p):return json.loads(p.read_bytes())

def command(proc,mode,radius,residual,audit,cap):
    r=dict(mode=mode,radius=radius,residual=residual,audit=audit,cap=cap)
    proc.stdin.write((json.dumps(r)+'\n').encode());proc.stdin.flush()
    line=proc.stdout.readline()
    if not line:raise RuntimeError(('native exit',proc.poll(),r))
    return json.loads(line)

def audit(r,image,gold,trace,ob,plans):
    baseline_hash=hashlib.sha256((gold/'state.json').read_bytes()).hexdigest()
    equivalences={}
    for key in ('rhs','writes','resumes'):equivalences[key]=r[key]==read(gold/f'{key}.json')
    unions=[e for run in read(ob/'events.json') for e in run if e[0]=='union']
    equivalences.update(unions=r['unions']==unions,graph=r['state_sha']==baseline_hash)
    with np.load(trace/'output.npz') as z:
        source=z['rhs'];runs=z['runs']
    with np.load(trace/'neural-inputs.npz') as z:pivot=z['pivot']
    exact=all(equivalences.values())
    ords=[t['ordinal'] for t in r['report']['tickets']]
    assert len(set(ords))==len(ords)==r['report']['counts']['committed']
    if exact:
        assert len(source)==r['report']['total_rhs'] and len(runs)==r['runs']
        for c in r['report']['tickets']:
            s=source[c['ordinal']-1];rid=int(s[1])
            assert (int(s[0]),rid)==(c['run'],c['rule']),(s[:2],c)
            assert not pivot[c['ordinal']-1] and plans[rid]['width']==c['width'] and c['width']>=2
            assert len(c['anchors'])==len(plans[rid]['linked']) and len(c['anchors'])>=2
    native=read(gold/'rhs.json');first=next((i+1 for i,(a,b) in enumerate(zip(r['rhs'],native)) if a!=b),None)
    if first is None and len(r['rhs'])!=len(native):first=min(len(r['rhs']),len(native))+1
    original=compile_program(image)
    expected=sum(1 for s in source if original[int(s[1])] is not None)
    supported=sum(1 for s in source if plans[int(s[1])] is not None)
    return dict(exact=exact,checks=equivalences,first_different_rhs_run=first,expected_multi_rhs=expected,source_rhs_with_supported_plan=supported,
                source_rhs=len(source),expected_runs=len(runs))

def main(a):
    a.out.mkdir(parents=True,exist_ok=False);summary={}
    for name in a.cases:
        anchor=name in ('sum-bits','dot-product')
        im=a.ref/f'release-input-{name}' if anchor else a.corpus/name/'input'
        program=a.ref/name/'program.json' if anchor else a.corpus/name/'program.json'
        gold=a.ref/f'oracle-{name}' if anchor else a.corpus/name/'reference'
        plans=(sealed_plans if a.sealed else compile_program)(im);pp=a.out/f'{name}-plans.json';pp.write_text(json.dumps(plans,separators=(',',':')))
        proc=subprocess.Popen([a.binary,program,pp,a.model],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        try:
            for arm in a.arms:
                mode,rad,execution=arm.split('-');radius=int(rad);residual=execution=='assist'
                detail=command(proc,mode,radius,residual,True,a.cap)
                evidence=audit(detail,im,gold,a.capture/name,a.corpus/name/'observation',plans)
                full=detail['report'];tickets=full.pop('tickets')
                if tickets:
                    with gzip.open(a.out/f'{name}-{arm}-provenance.json.gz','wt') as f:json.dump(tickets,f,separators=(',',':'))
                v=dict(evidence,**full,one_audit_ms=detail['ms'],runs=detail['runs'],state_sha=detail['state_sha'])
                v['ms']=[]
                for _ in range(a.repeats):
                    t=command(proc,mode,radius,residual,False,a.cap)
                    assert t['state_sha']==detail['state_sha'] and t['report']['counts']['committed']==full['counts']['committed']
                    v['ms'].append(t['ms'])
                if v['ms']:v['median_ms']=median(v['ms'])
                summary[name+'/'+arm]=v
                (a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
                print(name,arm,evidence['exact'],evidence['first_different_rhs_run'],full['counts']['committed'],full['counts']['exhausted'],detail['ms'],flush=True)
        finally:proc.stdin.close();proc.wait()
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','model','ref','corpus','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    p.add_argument('--arms',nargs='+',default=['learned-1-only','learned-2-only','learned-0-assist','wrong-1-assist','none-0-only'])
    p.add_argument('--sealed',action='store_true')
    p.add_argument('--repeats',type=int,default=0);p.add_argument('--cap',type=int,default=200000)
    main(p.parse_args())
