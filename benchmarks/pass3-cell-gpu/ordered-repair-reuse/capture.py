"""Confirm production work and occupancy without charging the detailed audit to the counters."""
import argparse,json
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
driver=run_path(str(HERE/'study.py'))
site,base,MODES=driver['site'],driver['base'],driver['MODES']


def capture(a):
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for case,modes in [('sum-bits',('all',)),('conjugate-gradient',('combined',)),('3mm',('all','combined','delayed-combined')),('deriche',('combined','delayed-combined'))]:
        p,plan,req=site.config(a,case)
        req.update(header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192)
        records={}
        with base.session(a.native,p,plan) as infer:
            for arm in modes:
                v=infer(dict(req,ordered_repair=MODES[arm],audit=False))
                q=v['ordered_repair']
                assert not q['work']['audit'] and not q['work']['payload_audits'] and not q['work']['audited_adoptions']
                records[arm]=dict(runs=v['runs'],rhs=v['multi']['total_rhs'],state_sha=v['state_sha'],root_allocated=v['root_recipe']['allocated'],repair_work=q)
        report[case]=records
        (a.out/'production.json').write_text(json.dumps(report,indent=1)+'\n')
        print(case,{k:v['repair_work']['work']['copied_payloads'] for k,v in records.items()},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;capture(a)
