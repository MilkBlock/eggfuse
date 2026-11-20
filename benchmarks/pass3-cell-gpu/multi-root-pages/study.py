"""Compare per-tuple and immutable per-rule pages, including corruption before source acceptance."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
from statistics import median
from time import perf_counter
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'compact-recipes'))
import study as ref


def evidence(record,gold):
    check=ref.compare(record,gold)
    assert check['aligned'] and check['neural_rhs']==gold['rhs_count']
    check['winners']=ref.digest([record['single']['committed'],record['multi']['tickets']])
    return {k:check[k] for k in ('checks','rhs','neural_rhs','fresh','direct_cells','state_sha','raw','commits','multi','physical','children','cells','winners','root_allocated','applied')}


def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for case in a.cases:
        b=a.bundles/f'{case}-1703'
        req=ref.read(b/'request.json')
        for name in ('single_config','merge_config'):req[name]=str(b/req[name])
        req.update(rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2),multi_mode='rowdeltapairguardstackseallearned',radius=0,packed_lookup=True,baked_row_index=False,
                   multi_weights=str(a.weights/f'{case}-1703-tied.json'),baked_codes=str(a.weights/f'{case}-1703-tied.bin'))
        with ExitStack() as stack:
            oracle=stack.enter_context(ref.session(a.vanilla/'vanilla-audit',b/'program.json'))
            gold=oracle({'audit':True})
            infer=stack.enter_context(ref.session(a.binary,b/'program.json',b/'plans.json'))
            for encoding in a.encodings:
                cfg=a.out/f'{case}-{encoding}.json'
                cfg.write_text(json.dumps(dict(encoding=encoding,control='use',forbid_fallback=True)))
                req['root_config']=str(cfg)
                base=evidence(infer(dict(req,audit=True,multi_root_pages=False)),gold)
                page=infer(dict(req,audit=True,multi_root_pages=True))
                assert evidence(page,gold)==base
                raw=page['multi']['counts']['raw_tuples']
                assert 'adaptive_rows' in page['single']
                assert raw==page['multi']['paged_tuples'] and 0<page['multi']['pages']<raw
                source=dict(evidence=base,pages=page['multi']['pages'],raw_tuples=raw,negative_controls={},ms={'separate_archive':[],'separate':[],'paged':[]})
                source["phases_ms"]={arm:[] for arm in source["ms"]}
                source["roundtrip_ms"]={arm:[] for arm in source["ms"]}
                source["pre_post_ms"]={arm:[] for arm in source["ms"]}
                del page
                for fault in (1,2,3):
                    failed=infer(dict(req,multi_root_pages=True,multi_root_fault=fault))
                    assert 'no verified root recipe' in failed['source_error'],failed.get('source_error')
                    source['negative_controls'][fault]=[failed['runs'],failed['source_error']]
                for trial in range(a.repeats+1):
                    order=['separate_archive','separate','paged'];i=trial%3;order=order[i:]+order[:i]
                    for arm in reversed(order) if trial%2 else order:
                        start=perf_counter()
                        v=infer(dict(req,multi_root_pages=arm=='paged',archive_single_winners=arm=='separate_archive'))
                        elapsed=(perf_counter()-start)*1000.
                        assert bool(v['single']['committed'])==(arm=='separate_archive')
                        assert v['state_sha']==base['state_sha'] and v['runs']==gold['runs']
                        assert v['multi']['counts']['raw_tuples']==raw and v['root_recipe']['allocated']==base['root_allocated']
                        if trial:
                            source['ms'][arm].append(v['ms'])
                            source['phases_ms'][arm].append(v['phases_ms'])
                            source['pre_post_ms'][arm].append(v['pre_post_ms'])
                            source['roundtrip_ms'][arm].append(elapsed)
                source['median_ms']={k:median(v) for k,v in source['ms'].items()}
                report[f'{case}/{encoding}']=source
                (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
                print(case,encoding,source['median_ms'],source['pages'],raw,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','vanilla','bundles','weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['jacobi-1d','conjugate-gradient'])
    p.add_argument('--encodings',nargs='+',default=['checked_slots'])
    p.add_argument('--repeats',type=int,default=6)
    main(p.parse_args())
