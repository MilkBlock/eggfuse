"""Source-ordered, parallel learned joins on current typed columns; independent original CPU reference."""
import argparse,json,importlib.util
from pathlib import Path
from statistics import median
from contextlib import ExitStack

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('pinned_policy',HERE.parent/'integrated-cpu-policy/measure.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def setup(a,case):
    prog,plan,_,r=base.setup(a,case)
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    req=base.query(r,'all',admission)
    req.update(forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),atom_constraints=2,
        tiered_ports=dict(primary=True,columns=True,evidence_views=1,bytes=1<<20))
    req['multi_mode']=req['multi_mode'].replace('seallearned','seal2xlearned')
    return prog,plan,req


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    for case in a.cases:
        prog,plan,req=setup(a,case)
        vanilla=a.exp/'compact-vanilla-20261121'
        with base.session(vanilla/'vanilla-audit',prog) as s:gold=s({'audit':True})
        with ExitStack() as ctx:
            orig=ctx.enter_context(base.session(vanilla/'vanilla',prog));infer=ctx.enter_context(base.session(a.native,prog,plan))
            configs={'original':req}
            if a.matrix=='packed':
                choices={str(w):dict(workers=w) for w in (1,2,4)}
            else:
                choices={'fresh1':dict(workers=1),'local':dict(workers=1,local=True,cache_bytes=4<<20)}
                for w in (1,2,4):choices[f'cached{w}']=dict(workers=w,cache_bytes=4<<20)
                for w in (2,4):choices[f'admit{w}']=dict(workers=w,cache_bytes=4<<20,min_cost=128)
                choices['grain4']=dict(workers=4,cache_bytes=4<<20,min_cost=128,grain=4)
            for name,options in choices.items():configs[name]=dict(req,join_workers=dict(min_roots=a.min_roots,**options))
            arms={'vanilla':dict(ms=[],rhs=gold['rhs_count'],graph=gold['state_sha'])};identity=None
            for name,cfg in configs.items():
                raw=infer(dict(cfg,audit=True))
                if 'source_error'in raw:raise RuntimeError((case,name,raw['source_error']))
                v=base.summarize(raw,gold);m=raw['multi']
                proof={k:v[k] for k in ('rhs','raw','multi','physical','commits','children','single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','direct_cells','state_sha')}
                proof.update(raw_sha=m['raw_sha256'],published=m['paged_tuples'],verified=m['counts']['verified_parent_tuples'],rejects=m['counts']['raw_parent_rejects'])
                if identity is None:identity=proof
                assert proof==identity,(case,name,[(k,proof[k],identity[k]) for k in proof if proof[k]!=identity[k]])
                work=m['worker_join']
                if name!='original':assert work['calls'] and work['raw'] and work['attempts']
                arms[name]=dict(ms=[],samples=[],identity=proof,fresh=v['fresh'],aligned=v['aligned'],audit=work)
            faults={}
            if case in ('sum-bits','dot-product'):
                for i,msg in [(1,'invalid learned worker frame generation'),(2,'invalid learned worker result offset')]:
                    failed=infer(dict(req,join_workers=dict(workers=2,min_roots=a.min_roots,fault=i)))
                    assert msg in failed.get('source_error',''),(case,i,failed.get('source_error'))
                    faults[str(i)]=dict(error=failed['source_error'],completed=failed['runs'])
            names=list(arms)
            for i in range(a.repeats+1):
                order=names[i%len(names):]+names[:i%len(names)]
                for name in order if i%2 else order[::-1]:
                    r=orig({}) if name=='vanilla' else infer(dict(configs[name],audit=False))
                    assert r['runs']==gold['runs'] and r['state_sha']==gold['state_sha']
                    if i:
                        arm=arms[name];arm['ms'].append(r['ms'])
                        if name not in ('original','vanilla'):
                            w=r['multi']['worker_join']
                            for k in ('calls','raw','attempts','speculative'):assert w[k]==arm['audit'][k]
                            arm['samples'].append({k:w[k] for k in ('preparation_ns','pool_start_ns','dispatch_ns','blocked_ns','worker_ns','merge_ns','peak_workers','peak_overlap','multicore_calls','worker_span_ns')})
                            if 'longest_lane_ns' in w:arm['samples'][-1]['longest_lane_ns']=w['longest_lane_ns']
            for arm in arms.values():arm['median_ms']=median(arm['ms'])
            result[case]=dict(arms=arms,threshold=a.min_roots,faults=faults)
            (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
            print(case,[(n,round(v['median_ms'],2),v.get('audit',{}).get('raw')) for n,v in arms.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('native','exp','out'):p.add_argument(n,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--matrix',choices=['packed','resident'],default='packed')
    p.add_argument('--repeats',type=int,default=6);p.add_argument('--min-roots',type=int,default=64)
    run(p.parse_args())
