"""Charge the API boundary, including fresh graph/model setup, final export, JSON transport and decoding."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
from statistics import median
from time import perf_counter
import importlib.util
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_wall',HERE.parent/'integrated-cpu-policy/measure.py')
ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)

def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    evidence=ref.read(a.evidence);report={}
    admission=ref.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    for case,proof in evidence.items():
        prog,plan,_,base=ref.setup(a,case)
        with ExitStack() as scope:
            vanilla=scope.enter_context(ref.session(a.exp/'compact-vanilla-20261121/vanilla',prog))
            engine=scope.enter_context(ref.session(a.binary,prog,plan))
            modes={'vanilla':(vanilla,{}),'exact':(engine,{'baseline':True}),
                   'control':(engine,ref.query(base,'all',admission)),'grouped':(engine,dict(ref.query(base,'all',admission),grouped_root=True))}
            arms={n:dict(execute_ms=[],wall_ms=[],pre_post_ms=[]) for n in modes}
            names=list(modes)
            for trial in range(5):
                i=trial%len(names);order=names[i:]+names[:i]
                for n in reversed(order) if trial%2 else order:
                    fn,req=modes[n];now=perf_counter();v=fn(req);wall=(perf_counter()-now)*1000.
                    assert v['state_sha']==proof['neural-off']['state'] and v['runs']==proof['vanilla']['runs']
                    if trial:
                        arms[n]['wall_ms'].append(wall);arms[n]['execute_ms'].append(v['ms'])
                        if n!='vanilla':arms[n]['pre_post_ms'].append(v['pre_post_ms'])
            for v in arms.values():
                v.update(wall_median=median(v['wall_ms']),execute_median=median(v['execute_ms']))
            report[case]=arms;(a.out/'wall.json').write_text(json.dumps(report,indent=1)+'\n')
            print(case,[(n,round(v['wall_median'],1)) for n,v in arms.items()],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for f in ('binary','exp','evidence','out'):p.add_argument(f,type=Path)
    run(p.parse_args())
