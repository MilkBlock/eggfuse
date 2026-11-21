"""Fit a producer-type gate on separate disjoint training programs using exact paid returns."""
import argparse,hashlib,json
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
joint=run_path(str(HERE.parent/'integral-filter-joint/study.py'))
def key(r):
    identity={field:r[field] for field in ('query','effects','slots','interface')}
    return hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def fitted(keys):
    # Deterministic sparse return estimator, one independent coefficient per
    # compiled producer schema. One committed saved packet is one unit of return.
    credits,exposures=keys[-1],keys[2]
    return credits/(exposures+4)

def run(a):
    a.out.mkdir(parents=True,exist_ok=True)
    table={};donors={}
    for case in ('dot-product','jacobi-1d'):
        program,plan,req=joint['src'].config(a,case)
        cfg=joint['settings'](req,'filter_mixed')
        rules=json.loads(program.read_bytes())['recipe']['rules']
        with joint['src'].base.session(a.native,program,plan) as infer:
            v=infer(dict(cfg,paid_families={'mode':'discovery'}))
        assert 'source_error' not in v,v.get('source_error')
        fam=v['paid_families'];d={}
        for rid,counts in fam['rules'].items():
            k=key(rules[int(rid)])
            old=table.setdefault(k,[0]*8)
            for i,n in enumerate(counts):old[i]+=n
            if counts[7]:d[k]=counts
        donors[case]={'sha':hashlib.sha256(program.read_bytes()).hexdigest(),'committed':sum(a[7] for a in d.values()),'observed':len(fam['rules'])}
        print(case,donors[case],flush=True)
    coefficients={k:fitted(v)for k,v in table.items() if v[-1]}
    kept=sorted(k for k,v in coefficients.items() if v>=0.01)
    (a.out/'policy.json').write_text(json.dumps({'donors':donors,'threshold':0.01,'pseudocount':4,'chosen':kept,'coefficients':coefficients,'training':{k:v for k,v in table.items() if v[-1]}},indent=1)+'\n')
    print('selected',len(kept),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','out'):p.add_argument(n,type=Path)
    run(p.parse_args())
