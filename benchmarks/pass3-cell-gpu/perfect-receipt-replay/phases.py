"""Measure the preserved source phases while replaying sealed addresses on a fresh graph."""
import argparse,importlib.util,json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_sites',HERE.parent/'pair-source-frontier/profile.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
FIELDS=('search','rhs','repair','publication','delivery')


def measure(a):
    a.out.mkdir(parents=True,exist_ok=False);data={}
    for case in a.cases:
        p,plan,req=source.config(a,case)
        req.update(header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192)
        with source.base.session(a.exp/'compact-vanilla-20261121/vanilla',p) as oracle:
            expected=oracle({})
        arms=['live','all','positive'];samples={k:[] for k in arms}
        with source.base.session(a.native,p,plan) as infer:
            captured=infer(dict(req,receipt_oracle='capture'));assert captured['state_sha']==expected['state_sha']
            for i in range(4):
                for arm in arms[i%3:]+arms[:i%3]:
                    v=infer(dict(req,receipt_oracle=arm))
                    assert v['state_sha']==expected['state_sha'] and v['multi']['total_rhs']==expected['rhs_count'] and v['runs']==expected['runs']
                    times=dict(zip(FIELDS,v['phases_ms']));times['inference']=v['ms']
                    times['outer']=v['ms']-sum(v['phases_ms'])
                    assert min(times.values())>=0
                    if i:samples[arm].append(times)
        data[case]=samples
        (a.out/'phases.json').write_text(json.dumps(data,indent=1)+'\n')
        print(case,[(k,{key:round(median(row[key] for row in v),1) for key in ('search','rhs','repair','inference')}) for k,v in samples.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('exp','native','out'):p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','conjugate-gradient','3mm'])
    a=p.parse_args();a.seed=1703;measure(a)
