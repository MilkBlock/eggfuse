"""Observe source-origin union roots on the complete original Pass 3, with frozen proposal gating."""
import argparse,hashlib,importlib.util,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_provenance',HERE.parent/'pair-source-frontier/profile.py')
source=importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
base=source.base
SOURCE=('raw','multi','commits','physical','children','cells','single_winners','multi_winners','root_parents','root_ids','nested_ids')


def collect(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    for case in a.cases:
        p,plans,req=source.config(a,case)
        req.update(header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4)
        with base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as independent:
            gold=independent(dict(audit=True))
        origins=[e for run in gold['unions'] for e in run]
        digest=0
        for tag,hi,lo in origins:
            assert tag=='union' and hi>lo
            for v in (hi,lo):digest=((digest^v)*1099511628211)&((1<<64)-1)
        if getattr(a,'point_control',False):
            modes={'parent-local':{'mode':'all'},'one-request':{'mode':'all','point':True}}
        elif getattr(a,'global_policy',None):
            modes=json.loads(a.global_policy.read_bytes())
            # A separate source-aligned native execution deploys each frozen threshold.
            for k in (a.omit or []):modes.pop(k)
        elif a.policy:
            weights=json.loads(a.policy.read_bytes())
            modes={'uniform':{'mode':'uniform','percent':25},
                   'static':{'mode':'static','percent':25},
                   **{name:{'mode':'model','percent':25,'weights':row['weights']} for name,row in weights.items()}}
        else:modes={'all':{'mode':'all','percent':100}}
        ref=None
        rows={}
        with base.session(a.native,p,plans) as infer:
            for arm,v in modes.items():
                out=infer(dict(req,union_position=v,audit=True))
                assert 'source_error' not in out,(case,arm,out.get('source_error'))
                audited=base.summarize(out,gold)
                assert all(audited['checks'].values()) and audited['rhs']==audited['neural_rhs']==gold['rhs_count']
                pos=out['union_position'];tot=pos['totals']
                assert tot['effective']==len(origins) and tot['union_hash']==digest,(case,tot['effective'],len(origins))
                assert tot['effective']==sum(v['effective'] for v in pos['origins'].values())
                assert pos['origins'].get('explicit',{}).get('attempts',0) >= tot['matched_explicit']
                assert tot['committed_input_pair']==tot['committed_pair_valid']
                assert tot['parent_pair_valid']==tot['parent_pair_known']
                claims={k:audited[k] for k in SOURCE+('checks','state_sha','rhs','direct_cells','fresh')}
                if ref is None:ref=claims
                else:assert ref==claims
                rows[arm]=pos
                del out
                print(case,arm,len(origins),pos['origins'],tot['parent_pair_known'],tot['choices'],flush=True)
            if getattr(a,'point_control',False):
                from statistics import median
                for r in rows.values():r['timed']=[]
                keys=list(modes)
                for rep in range(5):
                    for label in (keys if rep%2 else reversed(keys)):
                        measured=infer(dict(req,union_position=modes[label],audit=False))
                        assert measured['state_sha']==gold['state_sha'] and measured['runs']==gold['runs'] and measured['multi']['total_rhs']==gold['rhs_count']
                        native=measured['union_position']['totals']
                        assert native['union_hash']==digest and native['point_requests']==rows[label]['totals']['point_requests']
                        if rep:rows[label]['timed'].append(dict(inference_ms=measured['ms'],request_ms=native['point_ns']/1e6))
                print(case,[(k,round(median(v['inference_ms'] for v in r['timed']),2),round(median(v['request_ms'] for v in r['timed']),2)) for k,r in rows.items()],flush=True)
        result[case]=dict(ledger=ref,runs=gold['runs'],union_events=len(origins),union_hash=digest,arms=rows)
        (a.out/'results.json').write_text(json.dumps(result,separators=(',',':'))+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d'])
    p.add_argument('--point-control',action='store_true');p.add_argument('--global-policy',type=Path);p.add_argument('--omit',nargs='*');p.add_argument('--policy',type=Path);p.add_argument('--seed',type=int,default=1703)
    collect(p.parse_args())
