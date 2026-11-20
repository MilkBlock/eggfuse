"""Run frozen current learned policies and the original executor on new workloads."""
import argparse
from contextlib import ExitStack
import hashlib,importlib.util,json
from pathlib import Path
from statistics import median
from prepare import CASES
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_policy',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def first_delta(actual,expected):
    for i,(left,right) in enumerate(zip(actual,expected)):
        if left!=right:
            short=lambda v:v if len(str(v))<4500 else {'digest':hashlib.sha256(json.dumps(v,sort_keys=True).encode()).hexdigest(),'items':len(v),'sample':str(v)[:400]}
            return dict(index=i,actual=short(left),expected=short(right))
    if len(actual)!=len(expected):return dict(index=min(len(actual),len(expected)),actual_length=len(actual),expected_length=len(expected))
    return None


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    vd=a.exp/'compact-vanilla-20261121';tables=a.exp/'baked-port-packed-study-v1'
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    manifest=base.read(a.bundles/'manifest.json')
    for case in a.cases:
        bundle=a.bundles/f'{case}-1703';prog=bundle/'program.json';plan=bundle/'plans.json'
        request=base.read(bundle/'request.json')
        assert request['source_sha256']==manifest[case]['program']==hashlib.sha256(prog.read_bytes()).hexdigest()
        assert hashlib.sha256(plan.read_bytes()).hexdigest()==manifest[case]['plans']
        for f in ('single_config','multi_weights','merge_config','root_config'):request[f]=str(bundle/request[f])
        root=a.out/f'{case}-root.json';root.write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
        request.update(multi_weights=str(tables/'sum-bits-1703-tied.json'),baked_codes=str(tables/'sum-bits-1703-tied.bin'),
                       baked_row_index=False,packed_lookup=True,radius=0,root_config=str(root),
                       early_guards='constants',multi_mode='rowdeltapairguardstackseallearned',
                       rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=2))
        req=base.query(request,'all',admission)
        assert not req['multi_residual'] and not base.read(Path(req['single_config']))['residual']
        cfg={'baseline':req,'frozen':dict(req,forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),
                    multi_mode='rowdeltapairguardstackseal2xlearned',atom_constraints=2,
                    tiered_ports=dict(primary=True,columns=True,evidence_views=1,bytes=1<<20))}
        with base.session(vd/'vanilla-audit',prog) as original:gold=original({'audit':True})
        with ExitStack() as stack:
            original=stack.enter_context(base.session(vd/'vanilla',prog))
            engine=stack.enter_context(base.session(a.native,prog,plan))
            result={'vanilla':dict(ms=[],rhs=gold['rhs_count'],runs=gold['runs'],state_sha=gold['state_sha'])}
            arms=['vanilla']
            for mode,config in cfg.items():
                out=engine(dict(config,audit=True))
                if 'source_error' in out:
                    result[mode]=dict(aligned=False,error=out['source_error'],completed_runs=out['runs']);continue
                source_compare=base.summarize.__globals__['compare']
                precheck=source_compare(out,gold)
                if not (precheck['aligned'] and precheck['rhs']==precheck['neural_rhs']==gold['rhs_count']
                        and precheck['direct_cells']*100>=98*precheck['fresh']):
                    differences={k:first_delta(out[k],gold[k]) for k in ('rhs','writes','resumes','schedule')}
                    differences['unions']=first_delta([[e for e in group if e[0]=='union'] for group in out['events']],gold['unions'])
                    result[mode]=dict(status='failed_source_or_attribution',**precheck,differences=differences,counts=out['multi']['counts'])
                    print(case,mode,precheck['checks'],precheck['rhs'],precheck['neural_rhs'],precheck['direct_cells'],precheck['fresh'],differences,flush=True)
                    del out
                    continue
                v=base.summarize(out,gold);v.pop('rows');v.pop('work')
                v.update(counts=out['multi']['counts'],forward=out['multi']['forward'],tier=out['multi']['tier'])
                if mode=='frozen' and 'single_winners' in result['baseline']:
                    for k in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','rhs','direct_cells'):
                        assert v[k]==result['baseline'][k],(case,k)
                result[mode]=v;arms.append(mode);del out
            for lap in range(1+a.repeats):
                i=lap%len(arms);seq=arms[i:]+arms[:i]
                for label in seq if lap%2 else reversed(seq):
                    out=original({}) if label=='vanilla' else engine(dict(cfg[label],audit=False))
                    assert out['state_sha']==gold['state_sha'] and out['runs']==gold['runs']
                    if label!='vanilla':assert out['root_recipe']['allocated']==result[label]['root_allocated']
                    if lap:result[label]['ms'].append(out['ms'])
            for arm in arms:result[arm]['median_ms']=median(result[arm]['ms'])
        results[case]=result;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case, gold['rhs_count'], {k:round(v['median_ms'],2) if 'median_ms' in v else v.get('error') for k,v in result.items()},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','bundles','out'):p.add_argument(k,type=Path)
    p.add_argument('--repeats',type=int,default=6);p.add_argument('--cases',nargs='+',choices=CASES,default=CASES)
    run(p.parse_args())
