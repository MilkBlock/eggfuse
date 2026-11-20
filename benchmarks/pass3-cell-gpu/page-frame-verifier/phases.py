"""Measure integrated verifier subphases using native, separately instrumented rule timers."""
import argparse,json
from pathlib import Path
from statistics import median
from bench import HERE,MODES,base,request

def profile(a):
    a.out.mkdir(parents=True,exist_ok=False)
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    result={}
    for case in ('jacobi-1d','conjugate-gradient'):
        src,plan,_,req=base.setup(a,case)
        req['multi_mode']='profile'+req['multi_mode']
        with base.session(a.native,src,plan) as session:
            outcomes={}
            for i in range(4):
                names=['production','compact','compact-issued']
                order=names[i%3:]+names[:i%3]
                for name in order:
                    r=session(request(req,admission,MODES[name]))
                    p=r['multi']['rule_profile'];assert p is not None
                    values=[r['ms'],*[sum(x[k] for x in p) for k in ('frame_ms','issuance_ms','validation_ms')]]
                    if i:outcomes.setdefault(name,[]).append(values)
            result[case]={n:dict(measured_ms=[round(median(c),5) for c in zip(*rows)],samples=rows) for n,rows in outcomes.items()}
            print(case,{k:v['measured_ms'] for k,v in result[case].items()},flush=True)
    (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('native','exp','out'):ap.add_argument(n,type=Path)
    profile(ap.parse_args())
