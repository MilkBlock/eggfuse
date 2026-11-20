"""Break full source generation cost down by independent parent count and rule."""
import argparse,importlib.util,json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('integrated_source',HERE.parent/'integrated-cpu-policy/measure.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def config(a,case):
    small=case in ('sum-bits','dot-product','jacobi-1d','conjugate-gradient')
    seed=getattr(a,'seed',1703)
    b=(a.exp/('compact-holdouts-20261121-v1' if small else 'extra-pass3-transfer-v1'))/f'{case}-{seed}'
    p=b/'program.json'; req=base.read(b/'request.json');tables=a.exp/('baked-port-packed-study-v1' if seed==1703 else 'baked-port-speed-v2')
    for f in ('single_config','merge_config'):req[f]=str(b/req[f])
    root=a.out/(case+'-roots.json')
    root.write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
    req.update(multi_weights=str(tables/f'sum-bits-{seed}-tied.json'),baked_codes=str(tables/f'sum-bits-{seed}-tied.bin'),
               packed_lookup=True,baked_row_index=False,radius=0,root_config=str(root),early_guards='constants',
               rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=2),
               multi_mode='rowdeltapairguardstackseal2xlearned',multi_generation='complete')
    req=base.query(req,'all',base.read(HERE.parent/'single-signature-frontier/admission.json')['parameters'])
    req.update(forward=dict(columns=2,budget=4<<20,existence=True,freshness=True,min_candidates=8),atom_constraints=2,
               tiered_ports=dict(primary=True,columns=True,evidence_views=1,bytes=1<<20))
    return p,b/'plans.json',req
def run(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    for case in a.cases:
        p,plan,req=config(a,case);req['multi_mode']='profile'+req['multi_mode']
        with base.session(a.exp/'compact-vanilla-20261121/vanilla',p) as orig:gold=orig({})
        samples=[]
        with base.session(a.native,p,plan) as infer:
            for i in range(4):
                out=infer(req)
                assert out['state_sha']==gold['state_sha'] and out['runs']==gold['runs'] and out['multi']['total_rhs']==gold['rhs_count']
                if i:samples.append(out['multi']['rule_profile'])
        fields=list(samples[0][0]);rows=[{k:median([s[r][k] for s in samples]) for k in fields} for r in range(len(samples[0]))]
        report[case]=dict(rules=rows,counts=out['multi']['counts'],pair=out['multi']['pair_stats'])
        (a.out/'profile.json').write_text(json.dumps(report,separators=(',',':'))+'\n')
        print(case,[(i,round(r['issuance_ms'],1),int(r['picks']),int(r['raw'])) for i,r in sorted(enumerate(rows),key=lambda pair:-pair[1]['issuance_ms'])[:7]],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['jacobi-1d','conjugate-gradient','3mm','deriche'])
    run(p.parse_args())
