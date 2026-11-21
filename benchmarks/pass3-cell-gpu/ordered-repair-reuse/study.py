"""Charge ordered repair strategies to live learned source runs and independently audited endpoints."""
import argparse,importlib.util,json
from contextlib import ExitStack
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_frames',HERE.parent/'pair-source-frontier/profile.py')
site=importlib.util.module_from_spec(spec);spec.loader.exec_module(site)
base=site.base
MODES={'off':0,'reverse':1,'payload':2,'key':4,'all':7,'rebase':8,'defer':16,'combined':23,'delayed':32,'delayed-combined':53}
FIELDS=('search','rhs','repair','publication','delivery')


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    data={}
    for case in a.cases:
        program,plan,req=site.config(a,case)
        req.update(header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,multi_page_tuples=8192)
        configs={k:dict(req,ordered_repair=MODES[k]) for k in a.arms}
        original=a.exp/'compact-vanilla-20261121'
        with base.session(original/'vanilla-audit',program) as source:gold=source({'audit':True})
        with ExitStack() as stack:
            infer=stack.enter_context(base.session(a.native,program,plan))
            vanilla=stack.enter_context(base.session(original/'vanilla',program))
            report={'vanilla':dict(runs=gold['runs'],rhs=gold['rhs_count'],ms=[])}
            for arm,cfg in configs.items():
                v=infer(dict(cfg,audit=True))
                assert 'source_error' not in v,(arm,v.get('source_error'))
                row=base.summarize(v,gold);row.pop('rows');row.pop('work')
                row['counts']=v['multi']['counts']
                row['repair_work']=v['ordered_repair']
                row['phases']=[]
                if arm!='off':
                    ref=report['off']
                    for key in ('raw','multi','physical','commits','children','cells','state_sha','rhs','single_winners','multi_winners','root_parents','root_ids','nested_ids','direct_cells'):
                        assert row[key]==ref[key],(case,arm,key)
                    for f in ('repaired_dependencies','repair_collisions','repair_key_hash_changes'):
                        assert row['repair_work'][f]==ref['repair_work'][f],(case,arm,f)
                report[arm]=row
                del v
            names=list(report)
            for i in range(a.repeats+1):
                rotation=names[i%len(names):]+names[:i%len(names)]
                for arm in rotation if i%2 else reversed(rotation):
                    o=vanilla({}) if arm=='vanilla' else infer(configs[arm])
                    assert o['state_sha']==gold['state_sha'] and o['runs']==gold['runs']
                    if arm!='vanilla':
                        assert o['multi']['total_rhs']==gold['rhs_count']
                        assert o['root_recipe']['allocated']==report[arm]['root_allocated']
                        w=o['ordered_repair']['work'];assert not w['audit'] and not w['payload_audits']
                        if i:report[arm]['phases'].append(dict(zip(FIELDS,o['phases_ms'])))
                    if i:report[arm]['ms'].append(o['ms'])
            for arm,row in report.items():
                row['median_ms']=median(row['ms'])
                if arm!='vanilla':row['median_phases']={k:median(v[k] for v in row['phases']) for k in FIELDS}
        data[case]=report
        (a.out/'results.json').write_text(json.dumps(data,indent=1)+'\n')
        print(case,[(k,round(v['median_ms'],2),round(v.get('median_phases',{}).get('repair',0),2)) for k,v in report.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm'])
    p.add_argument('--arms',nargs='+',choices=MODES,default=list(MODES)[:5])
    p.add_argument('--repeats',type=int,default=4);p.add_argument('--seed',type=int,default=1703)
    a=p.parse_args();assert a.arms[0]=='off';run(a)
