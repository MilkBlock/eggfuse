"""Check actual source publication working sets on complete frozen two-view Pass-3 generation."""
import argparse,hashlib,importlib.util,json
from contextlib import ExitStack
from pathlib import Path
from statistics import median
from time import perf_counter_ns

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated',HERE.parent/'integrated-cpu-policy/measure.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
MODES={'original':None,'observed':0,'pending':1,'entries':2,'combined':3,'masks':4,'clean':5,'clean-only':6}


def inputs(a,name):
    external=name in ('3mm','deriche')
    bundle=(a.extra if external else a.exp/'compact-holdouts-20261121-v1')/(name+'-1703')
    program=bundle/'program.json';req=base.read(bundle/'request.json')
    assert req['source_sha256']==hashlib.sha256(program.read_bytes()).hexdigest()
    for k in ('single_config','multi_weights','merge_config','root_config'):req[k]=str(bundle/req[k])
    root=a.out/(name+'-root.json');root.write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
    tables=a.exp/'baked-port-packed-study-v1'
    req.update(multi_weights=str(tables/'sum-bits-1703-tied.json'),baked_codes=str(tables/'sum-bits-1703-tied.bin'),
        packed_lookup=True,baked_row_index=False,radius=0,root_config=str(root),early_guards='constants',
        multi_mode='rowdeltapairguardstackseallearned',rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=2))
    req=base.query(req,'all',base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters'])
    req.update(forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),
               atom_constraints=2,multi_mode='rowdeltapairguardstackseal2xlearned',tiered_ports=dict(primary=True,columns=True,bytes=1<<20,evidence_views=1),
               multi_generation='complete',multi_page_tuples=(8192 if external else 7))
    assert not req['multi_residual'] and not base.read(Path(req['single_config']))['residual']
    return program,bundle/'plans.json',req


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);results={};vd=a.exp/'compact-vanilla-20261121'
    for case in a.cases:
        program,plans,req=inputs(a,case);ts=base.read(program)['recipe']['tables']
        with base.session(vd/'vanilla-audit',program) as original:gold=original({'audit':True})
        with ExitStack() as ctx:
            original=ctx.enter_context(base.session(vd/'vanilla',program));session=ctx.enter_context(base.session(a.native,program,plans))
            arms={'vanilla':dict(rhs=gold['rhs_count'],graph=gold['state_sha'],ms=[])}
            explicit=session(dict(baseline=True,audit=True,reader_mode=0))
            for key in ('rhs','writes','resumes','runs','schedule','state_sha'):assert explicit[key]==gold[key],(case,'same-build exact',key)
            assert [[e for e in row if e[0]=='union'] for row in explicit['events']]==gold['unions']
            exact_publication=explicit['publication_readers']
            del explicit
            ident=None
            for name in a.arms:
                mode=MODES[name];cfg={} if mode is None else dict(reader_mode=mode)
                raw=session(dict(req,audit=True,**cfg))
                if 'source_error' in raw:raise RuntimeError((case,name,raw['source_error']))
                v=base.summarize(raw,gold);m=raw['multi'];report=raw['publication_readers'];s=report['reader']
                proof={k:v[k] for k in ('rhs','raw','multi','physical','commits','children','single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','direct_cells','state_sha')}
                proof.update(spine_events=sum(n for n,_ in raw['resumes']),effective_writes=sum(n for n,_ in raw['writes']),raw_issued=m['raw_sha256'],tuples=m['counts']['raw_tuples'],accepted=m['counts']['verified_parent_tuples'])
                if ident is None:ident=proof
                assert proof==ident,(case,name,[k for k in proof if ident[k]!=proof[k]])
                if s is not None:
                    origins=s.pop('by_origin',{});root={r[0] for r in raw['root_recipe']['fresh']}
                    nested={r['allocated'] for r in raw['merge_child']['issued'] if r['allocated'] is not None}
                    assert not root.intersection(nested)
                    by_source=[0,0,0]
                    for addr,count in origins.items():
                        cell=int(addr);by_source[0 if cell in root else 1 if cell in nested else 2]+=count
                    s['by_source']=by_source
                    if mode==3:assert sum(by_source)+s['origin_missing']==s['pending_omitted']
                    s['table_names']={n:[ts[int(n)]['name'],ts[int(n)]['kind']] for n in s['by_table']}
                arms[name]=dict(ms=[],aligned=v['aligned'],fresh=v['fresh'],proof=proof,
                    reader=s,equality=report.get('equality'),publication=report['publication'],columns=report['columns'],entry=report['entry'])
                del raw
            names=list(arms)
            for trial in range(a.repeats+1):
                order=names[trial%len(names):]+names[:trial%len(names)]
                for name in order if trial%2 else order[::-1]:
                    began=perf_counter_ns()
                    if name=='vanilla':raw=original({})
                    else:
                        mode=MODES[name];cfg={} if mode is None else dict(reader_mode=mode)
                        raw=session(dict(req,audit=False,**cfg))
                        assert raw['multi']['counts']['raw_tuples']==arms[name]['proof']['tuples']
                    assert raw['state_sha']==gold['state_sha'] and raw['runs']==gold['runs']
                    elapsed=(perf_counter_ns()-began)/1e6
                    if trial:
                        arms[name]['ms'].append(raw['ms']);arms[name].setdefault('wall_ms',[]).append(elapsed)
                        if name!='vanilla':
                            arms[name].setdefault('phases_ms',[]).append(raw['phases_ms'])
                            arms[name].setdefault('pre_post_ms',[]).append(raw['pre_post_ms'])
            for v in arms.values():v['median_ms']=median(v['ms'])
            meters={}
            if 'clean' in arms:
                for mode in (0,5):
                    samples=[]
                    for _ in range(3):
                        obs=session(dict(req,audit=False,reader_mode=mode,reader_clock=True))
                        assert obs['state_sha']==gold['state_sha'] and obs['runs']==gold['runs']
                        values=obs['publication_readers']['reader']['meter_ns']
                        assert all(v>0 for v in values)
                        samples.append([obs['ms'],*[v/1e6 for v in values]])
                    meters[str(mode)]=dict(samples=samples,median_ms=[median(col) for col in zip(*samples)])
            results[case]=dict(source_sha=req['source_sha256'],arms=arms,separate_profile=meters,same_build_native_publication=exact_publication)
            (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            print(case,[(n,round(v['median_ms'],2), (v.get('reader') or {}).get('pending_omitted')) for n,v in arms.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('native','exp','extra','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','deriche'])
    p.add_argument('--arms',nargs='+',choices=list(MODES),default=['original','observed','pending','entries','combined','masks'])
    p.add_argument('--repeats',type=int,default=4)
    run(p.parse_args())
