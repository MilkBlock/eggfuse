"""Pair the archived samples with an independent, identical-binary pass checking the full raw neural stream."""
from pathlib import Path
import argparse,json,hashlib,importlib.util
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('sparse_controls',HERE/'study.py')
trial=importlib.util.module_from_spec(s);s.loader.exec_module(trial)
common=trial.original.common;base=common.base


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    timed=base.read(a.timed)
    for case,arms in timed.items():
        p,plans,req=common.config(a,case);a.arms=[k for k in arms if k not in ('off','vanilla')]
        cfg=trial.choices(req,a)
        with base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as ref:gold=ref({'audit':True})
        observed={}
        with base.session(a.native,p,plans) as engine:
            for name,settings in cfg.items():
                out=engine(dict(settings,audit=True));v=base.summarize(out,gold);trial.inspect(name,out,v,observed);observed[name]=v
                for field in ('state_sha','raw','multi','physical','commits','children','cells','neural_rhs','direct_cells'):
                    assert v[field]==arms[name][field],(name,case,field)
                arms[name]['sparse']=v['sparse']
        report[case]=arms
        (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
        print(case,[(k,v['sparse']['admitted']) for k,v in arms.items() if k!='vanilla'],flush=True)
    (a.out/'provenance.json').write_text(json.dumps(dict(timing_sha256=hashlib.sha256(a.timed.read_bytes()).hexdigest(),
        binary_sha256=hashlib.sha256(a.native.read_bytes()).hexdigest()))+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','timed','out'):p.add_argument(k,type=Path)
    run(p.parse_args())
