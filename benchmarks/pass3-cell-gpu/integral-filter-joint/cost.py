"""Count actual learned-source and exact verifier work in normal uninstrumented requests."""
import argparse
import importlib.util
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('joint',HERE/'study.py');study=importlib.util.module_from_spec(sp);sp.loader.exec_module(study)

def run(a):
    a.out.mkdir(parents=True,exist_ok=True);reports={}
    for case in a.cases:
        prog,plan,req=study.src.config(a,case);rows={}
        with study.src.base.session(a.native,prog,plan) as infer:
            for name in study.MODES:
                v=infer(study.settings(req,name));s=v['single'];actor=s['adaptive_rows'];ic=v['integral_root']['counts']
                rows[name]=dict(decision_inputs=actor['stats']['source_headers'],regular_verifications=s['work'][2],
                    regular_point_reads=s['work'][3],regular_primitive_checks=s['work'][4],scalar_candidate_checks=sum(x['examined']for x in actor['scalar_certificates']),
                    scalar_key_reads=sum(x['reads']for x in actor['scalar_certificates']),delta_ports=ic['delta_ports'],anchor_reads=ic['anchor_reads'],
                    integral_suffix_reads=ic['point_reads'],integral_primitive_checks=ic['primitives'],integral_offers=ic['offers'],emitted=v['root_recipe']['emitted'],
                    state_sha=v['state_sha'],rhs=v['multi']['total_rhs'])
        reports[case]=rows
        (a.out/'cost.json').write_text(json.dumps(reports,indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('exp','native','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm'])
    run(p.parse_args())
