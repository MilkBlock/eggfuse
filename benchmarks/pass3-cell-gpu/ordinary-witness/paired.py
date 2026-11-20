"""Paired resident timings for native default, incremental verification and sealed complete tuples."""
import argparse
from pathlib import Path
import json
import subprocess
from statistics import median

from plan import compile_program,sealed_plans
from trial import command,audit

def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    summary={}
    arms={'native':('off',0),'prefix':('learned',2),'sealed':('seal3xlearned',2),'adaptive':('sealadaptive',3),
          'interval':('seal3xcertified',2)}
    for name in a.cases:
        anchor=name in ('sum-bits','dot-product')
        im=a.ref/f'release-input-{name}' if anchor else a.corpus/name/'input'
        program=a.ref/name/'program.json' if anchor else a.corpus/name/'program.json'
        gold=a.ref/f'oracle-{name}' if anchor else a.corpus/name/'reference'
        pp={};plans={};procs={}
        for nm,fn in [('prefix',compile_program),('sealed',sealed_plans)]:
            plans[nm]=fn(im);pp[nm]=a.out/f'{name}-{nm}.json';pp[nm].write_text(json.dumps(plans[nm],separators=(',',':')))
            procs[nm]=subprocess.Popen([a.binary,program,pp[nm],a.model],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        results={}
        try:
            for key,(mode,radius) in arms.items():
                shape='sealed' if mode.startswith('seal') else 'prefix'
                audited=command(procs[shape],mode,radius,False,True,a.cap)
                check=audit(audited,im,gold,a.capture/name,a.corpus/name/'observation',plans[shape])
                assert check['exact'],(key,name,check)
                r=audited['report'];tickets=r.pop('tickets')
                # Deterministic independent reset with every raw certificate hashed
                # upstream of the equality checker, and each actual source ordinal.
                second=command(procs[shape],mode,radius,False,True,a.cap)
                assert audited['state_sha']==second['state_sha'] and r['raw_sha256']==second['report']['raw_sha256']
                assert tickets==second['report']['tickets'] and r['counts']==second['report']['counts']
                examples={}
                for t in tickets:examples.setdefault(str(t['width']),t)
                results[key]=dict(check,ms=[],sha=audited['state_sha'],raw_replay_equal=True,examples=examples,**r)
            keys=list(arms)
            for i in range(a.reps):
                order=keys[i%len(keys):]+keys[:i%len(keys)]
                for key in order if i<len(keys) else order[::-1]:
                    mode,radius=arms[key];shape='sealed' if mode.startswith('seal') else 'prefix'
                    measured=command(procs[shape],mode,radius,False,False,a.cap)
                    assert measured['state_sha']==results[key]['sha'] and measured['report']['counts']==results[key]['counts']
                    results[key]['ms'].append(measured['ms'])
            for key in keys:results[key]['median_ms']=median(results[key]['ms'])
        finally:
            for proc in procs.values():proc.stdin.close();proc.wait()
        summary[name]=results
        (a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
        print(name,[(k,round(v['median_ms'],1),v['neural_committed']) for k,v in results.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','model','ref','corpus','capture','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--cap',type=int,default=1000000);p.add_argument('--reps',type=int,default=10)
    main(p.parse_args())
