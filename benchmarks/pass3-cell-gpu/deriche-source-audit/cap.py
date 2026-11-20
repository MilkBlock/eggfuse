"""Distinguish proposal budget truncation from a source semantic difference on Deriche."""
import argparse,json,sys
from collections import Counter,defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'compact-recipes'))
from study import session,digest,read

def run(a):
    a.out.mkdir(parents=True,exist_ok=False);bundle=a.bundle;prog=bundle/'program.json'
    req=read(bundle/'request.json');root=a.out/'root.json'
    root.write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
    for f in ('single_config','merge_config'):req[f]=str(bundle/req[f])
    req.update(root_config=str(root),multi_weights=str(a.exp/'baked-port-packed-study-v1/sum-bits-1703-tied.json'),
               baked_codes=str(a.exp/'baked-port-packed-study-v1/sum-bits-1703-tied.bin'),baked_row_index=False,packed_lookup=True,radius=0,
               early_guards='constants',multi_mode='rowdeltapairguardstackseallearned',multi_root_pages=True,
               rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=2,signature_frontier=True))
    cfg=read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    req.update(signature_frontier=dict(cfg,typed_bytes=262144,changed_ports=True,changed_epochs=True,fresh_build=True))
    gold=None
    if a.full:
        with session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog) as oracle:gold=oracle({'audit':True})
    report={};source=None
    with session(a.binary,prog,bundle/'plans.json') as call:
        for cap in a.caps:
            q=dict(req,cap=cap) if cap else {'baseline':True}
            v=call(dict(q,stop_after=None if a.full else a.run,watch_run=a.run,audit=a.full and cap!=0));debug=v['diagnostic']
            by_rule=defaultdict(list)
            for rid,row in debug['rows']:by_rule[rid].append(row)
            if cap==0:source=by_rule
            delta={}
            for rid in sorted(set(source)|set(by_rule)):
                expected=source.get(rid,[]);got=by_rule.get(rid,[])
                if got==expected:continue
                a1=Counter(json.dumps(x,sort_keys=True) for x in expected);b1=Counter(json.dumps(x,sort_keys=True) for x in got)
                delta[rid]=dict(expected=len(expected),actual=len(got),missing_count=sum((a1-b1).values()),extra_count=sum((b1-a1).values()),
                                missing=next(iter(a1-b1),None),extra=next(iter(b1-a1),None))
            record=dict(cap=cap,run=a.run,rhs=len(debug['rows']),rules={r:len(rows) for r,rows in by_rule.items()},delta=delta,exhausted=debug['cap'],state=v['state_sha'],row_sha=digest(debug['rows']))
            if gold is not None:
                from study import compare
                if cap:
                    audit=compare(v,gold);record['full_checks']={k:audit[k] for k in ('checks','aligned','rhs','neural_rhs','fresh','direct_cells')}
                record['runs']=v['runs']
            report[str(cap)]=record
            (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
            print(cap,record['rhs'],delta,debug['cap'][-8:],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('binary','exp','bundle','out'):p.add_argument(k,type=Path)
    p.add_argument('--full',action='store_true');p.add_argument('--caps',nargs='+',type=int,default=[0,1000000,8000000]);p.add_argument('--run',type=int,default=819)
    run(p.parse_args())
