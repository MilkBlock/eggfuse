"""Distinguish bounded exhaustion from complete enumeration and immutable physical paging."""
import argparse
from contextlib import ExitStack
import hashlib,importlib.util,json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('integrated',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(s);s.loader.exec_module(base)


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for name in a.cases:
        large=name=='deriche'
        b=(a.extra if large else a.exp/'compact-holdouts-20261121-v1')/(name+'-1703')
        p=b/'program.json';req=base.read(b/'request.json');assert hashlib.sha256(p.read_bytes()).hexdigest()==req['source_sha256']
        for k in ('single_config','multi_weights','merge_config','root_config'):req[k]=str(b/req[k])
        root=a.out/(name+'-root.json');root.write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
        tables=a.exp/'baked-port-packed-study-v1'
        req.update(multi_weights=str(tables/'sum-bits-1703-tied.json'),baked_codes=str(tables/'sum-bits-1703-tied.bin'),
                   packed_lookup=True,baked_row_index=False,radius=0,root_config=str(root),early_guards='constants',
                   multi_mode='rowdeltapairguardstackseallearned',rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=2))
        req=base.query(req,'all',base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters'])
        assert not req['multi_residual'] and not base.read(Path(req['single_config']))['residual']
        vd=a.exp/'compact-vanilla-20261121'
        with base.session(vd/'vanilla-audit',p) as native:gold=native({'audit':True})
        with ExitStack() as stack:
            infer=stack.enter_context(base.session(a.native,p,b/'plans.json'));original=stack.enter_context(base.session(vd/'vanilla',p))
            finite=1000000 if large else 2
            fail=infer(dict(req,cap=finite,multi_generation='bounded',audit=False))
            assert 'unexplored branch' in fail.get('source_error','') and 'state_sha' not in fail,fail.get('ms')
            result={'bounded':{k:fail[k] for k in ('source_error','runs','partial_rhs')}}
            if not large:
                prior=dict(req, cap=finite,audit=False);prior.pop('multi_generation',None)
                old=infer(prior);assert old['source_error']==fail['source_error']
                result['bounded']['legacy_limit_rejected']=True
            cases={'complete':dict(cap=finite,multi_generation='complete'),
                   'paged':dict(cap=finite,multi_generation='complete',multi_page_tuples=(8192 if large else 7))}
            good=dict(req,forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),
                      atom_constraints=2,multi_mode='rowdeltapairguardstackseal2xlearned',
                      tiered_ports=dict(primary=True,columns=True,bytes=1<<20,evidence_views=1),
                      cap=finite,multi_generation='complete',multi_page_tuples=(8192 if large else 7))
            requests={k:dict(req,**v) for k,v in cases.items()};requests['frozen']=good
            for label,q in requests.items():
                out=infer(dict(q,audit=True));v=base.summarize(out,gold);v.pop('work');v.pop('rows')
                v.update(page_count=out['multi']['pages'],max_page=out['multi']['max_sealed_page'],raw_packets=out['multi']['counts']['raw_tuples'])
                if label!='complete':
                    for f in ('cells','single_winners','multi_winners','root_parents','root_ids','nested_ids','direct_cells','rhs'):
                        assert result['complete'][f]==v[f],(name,label,f)
                    assert v['max_page']<=q['multi_page_tuples']
                    if label=='paged':
                        for f in ('raw','multi','commits','physical','children','raw_packets'):
                            assert v[f]==result['complete'][f],(name,f)
                        assert v['page_count']>result['complete']['page_count']
                result[label]=v;del out
            result['vanilla']=dict(ms=[],rhs=gold['rhs_count'],runs=gold['runs'])
            seq0=['vanilla',*requests]
            for trial in range(1+a.repeats):
                i=trial%len(seq0);seq=seq0[i:]+seq0[:i]
                for label in seq if trial%2 else reversed(seq):
                    out=original({}) if label=='vanilla' else infer(dict(requests[label],audit=False))
                    assert out['state_sha']==gold['state_sha'] and out['runs']==gold['runs']
                    if label!='vanilla':assert out['root_recipe']['allocated']==result[label]['root_allocated']
                    if trial:result[label]['ms'].append(out['ms'])
            for label in seq0:result[label]['median_ms']=median(result[label]['ms'])
            report[name]=result;(a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
            print(name,fail['source_error'],{k:round(result[k]['median_ms'],2) for k in seq0},flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','extra','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','deriche']);p.add_argument('--repeats',type=int,default=4)
    run(p.parse_args())
