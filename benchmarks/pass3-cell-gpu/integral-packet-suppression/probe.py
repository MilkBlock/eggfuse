"""Exercise an independently released closed occurrence on the real frozen singleton issuer."""
import argparse
import importlib.util
import json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('source_profile',HERE.parent/'pair-source-frontier/profile.py');src=importlib.util.module_from_spec(sp);sp.loader.exec_module(src)
def run(a):
    a.out.mkdir(parents=True,exist_ok=True);results={}
    for case in a.cases:
        prog,plan,req=src.config(a,case);req.update(header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,multi_page_tuples=8192,proposal_wave=65536,integral_root='apply')
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog) as get:gold=get(dict(audit=True))
        rows={}
        for name,enabled in [('external',False),('closed',True)]:
            with src.base.session(a.native,prog,plan) as infer:v=infer(dict(req,audit=True,birth_ledger=True,integral_packets=enabled))
            assert 'source_error' not in v,v.get('source_error')
            q=src.base.summarize(v,gold);del q['rows'],q['work']
            b=v['constructor_births'];ids={e[0] for e in b['rows'] if e[3] and e[7]&1}
            vis={e[0] for e in b['endpoint'] if e[-1]==0}
            payload=v['merge_child']
            q.update(internal=v['integral_packets'],births=len(ids),survivors=len(ids&vis),
                     merge_decisions=len(payload['issued']),merge_selected=sum(int(e['selected']) for e in payload['issued']),
                     scores=v['single']['adaptive_rows']['decision_digest'],source_serials=[v['root_recipe']['emitted'],v['single']['adaptive_rows']['stats']['emitted']],
                     birth_trace=src.base.summarize.__globals__['digest'](b['rows']),end_trace=src.base.summarize.__globals__['digest'](b['endpoint']))
            rows[name]=q
            print(case,name,q['emitted'],q['births'],q['survivors'],q['internal'],flush=True)
        base,on=rows['external'],rows['closed'];cnt=on['internal']['counts']
        for k in ('checks','single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','rhs','direct_cells','children','multi','state_sha','scores','births','survivors','birth_trace','end_trace','commits','physical','merge_decisions','merge_selected'):
            assert base[k]==on[k],(case,k)
        assert base['emitted'][1]==on['emitted'][1] and base['emitted'][0]-on['emitted'][0]==cnt['closed_lanes']==cnt['delivered']==cnt['original_checks']
        assert cnt['confirmed']+on['internal']['uncommitted_internal']==cnt['delivered']
        if cnt['delivered']:
            with src.base.session(a.native,prog,plan) as infer:fault=infer(dict(req,integral_packets=True,integral_release_fault=True))
            assert 'integral release epoch or watermark mismatch' in fault.get('source_error','')
            rows['fault']=dict(runs=fault['runs'],error=fault['source_error'])
        with src.base.session(a.native,prog,plan) as infer:
            for lap in range(a.repeats+1):
                for n in (['external','closed'] if lap%2 else ['closed','external']):
                    v=infer(dict(req,integral_packets=n=='closed'))
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if lap:rows[n].setdefault('inference_ms',[]).append(v['ms'])
        results[case]=rows;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,'complete',[(n,median(rows[n]['inference_ms']))for n in ('external','closed')],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits']);p.add_argument('--repeats',type=int,default=3)
    run(p.parse_args())
