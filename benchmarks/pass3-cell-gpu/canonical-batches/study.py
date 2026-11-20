"""Compare each canonicalization path on the same complete source and allocated Cell ledger."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_canon',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def dh(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def run(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    admission=base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters']
    for case in a.cases:
        b=a.exp/'extra-pass3-transfer-v1'/f'{case}-1703';p=b/'program.json';req=base.read(b/'request.json');w=a.exp/'baked-port-packed-study-v1'
        for k in ('single_config','merge_config'):req[k]=str(b/req[k])
        root=a.out/f'{case}-root.json';root.write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
        req.update(root_config=str(root),multi_weights=str(w/'sum-bits-1703-tied.json'),baked_codes=str(w/'sum-bits-1703-tied.bin'),
                   packed_lookup=True,baked_row_index=False,radius=0,multi_generation='complete',multi_mode='rowdeltapairguardstackseal2xlearned',
                   early_guards='constants',rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=2))
        req=base.query(req,'all',admission);req.update(forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),
               atom_constraints=2,tiered_ports=dict(primary=True,columns=True,evidence_views=1,bytes=1<<20))
        vd=a.exp/'compact-vanilla-20261121'
        with base.session(vd/'vanilla-audit',p) as oracle:gold=oracle({'audit':True})
        names={0:'source',1:'coarse',2:'direct',3:'memo',4:'combined'} if not a.frames else {0:'off',1:'sealed_inputs',2:'derived',3:'derived_direct'}
        def variant(number):
            return dict(canon_mode=number if not a.frames else (2 if number==3 else 0),canon_frame=(min(number,2) if a.frames else 0))
        arms={};common=None
        with ExitStack() as sc:
            native=sc.enter_context(base.session(a.native,p,b/'plans.json'));vanilla=sc.enter_context(base.session(vd/'vanilla',p))
            unmodified=sc.enter_context(base.session(a.exp/'segmented-complete-v3/session',p,b/'plans.json'))
            native_gold=native(dict(baseline=True,audit=True))
            for k in ('rhs','writes','resumes','state_sha','schedule','runs'):assert native_gold[k]==gold[k]
            assert [[ev for ev in row if ev[0]=='union'] for row in native_gold['events']]==gold['unions']
            arms['exact']=dict(ms=[],wall=[],phases=[],state=native_gold['state_sha'],fresh=native_gold['new_cells'],
                allocation_digest=dh(native_gold['allocations']))
            del native_gold
            arms['pinned']=dict(ms=[],wall=[],phases=[],state=gold['state_sha'])
            arms['vanilla']=dict(ms=[],wall=[],runs=gold['runs'],rhs=gold['rhs_count'],state=gold['state_sha'])
            for number in a.modes:
                arm=names[number]
                v=native(dict(req,**variant(number),canon_audit=False,canon_check=bool(number),audit=True))
                q=base.summarize(v,gold)
                identity={k:q[k] for k in ('neural_rhs','fresh','direct_cells','cells','state_sha','root_parents','root_ids','nested_ids','single_winners','multi_winners','raw','multi','commits','physical','children')}
                identity.update(per_rhs_allocations=dh(v['allocations']),new_cells=v['new_cells'])
                if common is None:common=identity
                else:assert identity==common,(case,arm)
                del v
                diag=native(dict(req,**variant(number),canon_audit=True))
                assert diag['state_sha']==gold['state_sha'] and diag['runs']==gold['runs']
                arms[arm]=dict(ms=[],wall=[],phases=[],work=diag['canon_work'],checks=q['checks'],identity=identity)
                if a.frames:
                    arms[arm]['frame']=diag['canon_frame'];arms[arm]['extra_contains']=diag['canon_contains']
                print(case,arm,'phase work',diag['canon_work']['phase'][1:],diag.get('canon_frame'),flush=True)
            seq=list(arms)
            for rep in range(a.repeats+1):
                n=rep%len(seq);order=seq[n:]+seq[:n]
                for arm in reversed(order) if rep%2 else order:
                    begin=perf_counter()
                    if arm=='vanilla':v=vanilla({})
                    elif arm=='pinned':v=unmodified(req)
                    elif arm=='exact':v=native(dict(baseline=True))
                    else:v=native(dict(req,**variant(next(k for k,name in names.items() if name==arm))))
                    elapsed=1000*(perf_counter()-begin)
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                    if rep:
                        arms[arm]['ms'].append(v['ms']);arms[arm]['wall'].append(elapsed)
                        if arm!='vanilla':arms[arm]['phases'].append(v['phases_ms'])
            for arm,out in arms.items():
                out['median_ms']=median(out['ms']);out['median_wall']=median(out['wall'])
                if arm!='vanilla':out['phase_medians']=list(map(median,zip(*out['phases'])))
            report[case]=arms;(a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
            print(case,[(k,round(v['median_ms'],1)) for k,v in arms.items()],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('native','exp','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['3mm','deriche'])
    p.add_argument('--frames',action='store_true');p.add_argument('--modes',nargs='+',type=int,default=[0,1,2,3,4])
    p.add_argument('--repeats',type=int,default=4)
    run(p.parse_args())
