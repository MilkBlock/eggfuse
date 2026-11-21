"""Time issuance and verification in the full live/oracle source execution, separately from primary medians."""
import argparse,importlib.util,json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('joint_run',HERE/'study.py');entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);data={}
    for case in a.cases:
        p,plan,req=entry.source.config(a,case)
        q=dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192,factor_page=0)
        q['multi_mode']='profile'+q['multi_mode']
        extra=dict(factor_page=2,page_premises=9,coordinate_verify=2,ordered_effect_blocks=4,ordered_repair=7)
        cfg={f'{r}-{k}':dict(q,**ext,receipt_oracle=r) for r in ('live','positive') for k,ext in [('original',{}),('joint',extra)]}
        vals={k:[] for k in cfg};names=list(cfg)
        with entry.source.base.session(a.exp/'compact-vanilla-20261121/vanilla',p) as ref:gold=ref({})
        with entry.source.base.session(a.native,p,plan) as infer:
            cap=infer(dict(q,receipt_oracle='capture'));assert cap['state_sha']==gold['state_sha']
            for i in range(4):
                for name in names[i:]+names[:i]:
                    v=infer(cfg[name]);assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs'] and v['multi']['total_rhs']==gold['rhs_count']
                    if i:
                        w={key:sum(r[key] for r in v['multi']['rule_profile']) for key in ('frame_ms','issuance_ms','validation_ms')}
                        vals[name].append(dict(w,**dict(zip(entry.PHASES,v['phases_ms'])),inference=v['ms']))
        data[case]=vals;(a.out/'phases.json').write_text(json.dumps(data,indent=1)+'\n')
        print(case,[(n,round(median(x['validation_ms'] for x in rows),2),round(median(x['rhs'] for x in rows),2)) for n,rows in vals.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['3mm']);a=p.parse_args();a.seed=1703;run(a)
