"""Ablate immutable frame offsets and one exact shared parent inside each real issued page."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
from statistics import median
from time import perf_counter

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_baseline',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
MODES={'production':None,'source':0,'frame':1,'prefix':2,'frame-prefix':3,'tail':4,'receipt':5,'tail-receipt':6,'frame-tail-receipt':7,'borrowed-receipt':8,'issued-ports':9,'compact':10,'compact-issued':11}


def request(req,admission,mode,audit=False,fault=0):
    r=base.query(req,'changed',admission,audit)
    if mode is not None:r['page_reader']=dict(mode=mode,fault=fault)
    return r


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    native=a.exp/'compact-vanilla-20261121'
    for case in a.cases:
        src,plan,_,req=base.setup(a,case)
        with base.session(native/'vanilla-audit',src) as ref:gold=ref({'audit':True})
        with ExitStack() as ctx:
            vanilla=ctx.enter_context(base.session(native/'vanilla',src))
            session=ctx.enter_context(base.session(a.native,src,plan))
            arms={'vanilla':dict(ms=[],rhs=gold['rhs_count'],graph=gold['state_sha'])}
            expected=None
            for name in a.arms:
                mode=MODES[name]
                r=session(request(req,admission,mode,True))
                if 'source_error' in r:raise RuntimeError((case,name,r['source_error']))
                v=base.summarize(r,gold)
                m=r['multi'];stats=m['page_reads']
                equiv={k:v[k] for k in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','rhs','direct_cells','state_sha','cells')}
                equiv.update(raw_choice=m['raw_sha256'],root_raw=r['root_recipe']['raw_hash'],paged=m['paged_tuples'],
                             raw_tuples=m['counts']['raw_tuples'],verified=m['counts']['verified_parent_tuples'],
                             parent_rejects=m['counts']['raw_parent_rejects'],single=r['single']['adaptive_rows']['decision_digest'])
                if expected is None:expected=equiv
                assert expected==equiv,(case,name,[k for k in equiv if equiv[k]!=expected[k]])
                assert round(100*v['direct_cells']/v['fresh'],3)>=98
                if mode in (1,3,7):assert stats['frame_rows']>0 and not stats['fresh_rejects'] and not stats['pointer_rejects']
                if mode in (2,3):assert stats['prefix_hits']>0
                if mode in (4,6,7,8,9,10,11):assert stats['dead_port_calls']>0
                if mode in (5,6,7,8,9,10,11):assert stats['seals'][0]>0
                if mode in (9,11):assert stats['issue_frame_refs']>0 and not stats['issue_offset_mismatches'] and stats['issue_frame_refs']+stats['issue_source_refs']==stats['parents']
                arms[name]=dict(ms=[],wall_ms=[],identity=equiv,page_reads=stats,physical_decodes=r['physical_decodes'],
                                fresh=v['fresh'],rhs=v['rhs'],direct=v['direct_cells'],aligned=True)
            faults={}
            if case in ('sum-bits','dot-product'):
                for fault in (1,2,3):
                    r=session(request(req,admission,1,False,fault))
                    if 'source_error' in r:
                        faults[fault]=dict(error=r['source_error'],runs=r['runs'])
                    else:
                        st=r['multi']['page_reads']
                        assert r['state_sha']!=gold['state_sha'] and st['pointer_rejects']+st['fresh_rejects']>0
                        faults[fault]=dict(graph=r['state_sha'],runs=r['runs'],pointer_rejects=st['pointer_rejects'],fresh_rejects=st['fresh_rejects'])
            if ('receipt' in a.arms or 'borrowed-receipt' in a.arms) and case in ('sum-bits','dot-product'):
                for fault in (1,2,3):
                    control=request(req,admission,8 if 'borrowed-receipt' in a.arms else 5)
                    r=session(dict(control,multi_root_fault=fault))
                    assert "no verified root recipe" in r.get("source_error",""), (case,fault,r.get("source_error"))
                    faults[f'root-{fault}']=dict(error=r['source_error'],runs=r['runs'])
            names=list(arms)
            for i in range(a.repeats+1):
                seq=names[i%len(names):]+names[:i%len(names)]
                for name in seq if i%2 else seq[::-1]:
                    start=perf_counter();r=vanilla({}) if name=='vanilla' else session(request(req,admission,MODES[name]))
                    elapsed=(perf_counter()-start)*1000
                    assert r['state_sha']==gold['state_sha'] and r['runs']==gold['runs']
                    if name!='vanilla':
                        audit_stats=arms[name]['page_reads'];actual_stats=r['multi']['page_reads']
                        if isinstance(actual_stats.get('seals'),list) and len(actual_stats['seals'])==4:
                            assert all(actual_stats[k]==audit_stats[k] for k in actual_stats if k not in ('seals','audit_anchor_lists_omitted','audit_anchor_refs_omitted'))
                            assert actual_stats['seals'][:3]==audit_stats['seals'][:3]
                        else:assert actual_stats==audit_stats
                        arms[name]['production_page_reads']=actual_stats
                        arms[name]['production_decodes']=r['physical_decodes']
                    if i:
                        arms[name]['ms'].append(r['ms'])
                        if name!='vanilla':arms[name]['wall_ms'].append(elapsed)
            for arm in arms.values():arm['median_ms']=median(arm['ms'])
            report[case]=dict(arms=arms,faults=faults)
            (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
            print(case,[(k,round(s['median_ms'],2)) for k,s in arms.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('native','exp','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--arms',nargs='+',choices=list(MODES),default=['production','source','frame','prefix','frame-prefix'])
    p.add_argument('--repeats',type=int,default=6)
    run(p.parse_args())
