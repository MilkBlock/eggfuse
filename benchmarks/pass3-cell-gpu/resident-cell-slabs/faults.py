"""Check actual held-out-of-model sum-bits source and the four authenticated-group fault controls."""
import argparse,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
source=importlib.util.spec_from_file_location('group_native',HERE.parent/'group-named-cells/study.py')
group=importlib.util.module_from_spec(source);source.loader.exec_module(group)

def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    program,plans,req=group.wave.parent.common.config(a,'sum-bits')
    with group.wave.parent.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',program) as ref: gold=ref({'audit':True})
    cfg=group.settings(req,a)['group'];report={}
    with group.wave.parent.base.session(a.native,program,plans) as infer:
        for arm,options in [('moving',{}),('resident',{'resident_headers':True,'page_width':64}),
                            *((fault,{'resident_headers':True,'page_width':64,'fault':fault})
                              for fault in ('stale','foreign','withheld','duplicate'))]:
            v=infer(dict(cfg,spec_cells=dict(cfg['spec_cells'],**options),audit=True))
            assert 'source_error' not in v,v.get('source_error')
            q=group.wave.parent.base.summarize(v,gold);q.pop('work');q.pop('rows')
            report[arm]=q;q['resident']=v['resident_slabs'];q['staging']=v['spec_cells']['counts']
            if arm!='moving':
                for k in ('rhs','raw','commits','physical','root_parents','root_ids','nested_ids','cells','state_sha','children','multi','wire_hash'):
                    assert q[k]==report['moving'][k],(arm,k)
            print(arm,q['resident']['published'],q['resident']['old_run_reads'],q['resident']['held_holes'],flush=True)
    (a.out/'faults.json').write_text(json.dumps(report,indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','weights','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;a.cap=8192;a.policy=json.loads(a.weights.read_bytes());run(a)
