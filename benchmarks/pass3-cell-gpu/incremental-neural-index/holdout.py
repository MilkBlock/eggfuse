"""Frozen larger source, actual production allocator and full joint witness/physical provenance."""
import argparse
from contextlib import ExitStack
import importlib.util
import json
import subprocess
import hashlib
import numpy as np
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('compact',HERE.parent/'compact-recipes/study.py')
ref=importlib.util.module_from_spec(spec);spec.loader.exec_module(ref)
read=ref.read


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for case in a.cases:
        for seed in a.seeds:
            b=a.holdout/f'{case}-{seed}';req=read(b/'request.json')
            for k in ('single_config','multi_weights','merge_config','root_config'):req[k]=str(b/req[k])
            if a.tied_packed:
                weights=read(Path(req['multi_weights']))
                tied=((np.asarray(weights['q'],np.float32)+np.asarray(weights['k'],np.float32))*np.float32(.5)).tolist()
                w=a.out/f'{case}-{seed}-weights.json';w.write_text(json.dumps(dict(weights,q=tied,k=tied)))
                lut=a.out/f'{case}-{seed}-baked.bin'
                subprocess.run([a.native.parent/'bake',w,lut],check=True,stdout=subprocess.DEVNULL)
                req.update(multi_weights=str(w),radius=0,baked_codes=str(lut),baked_row_index=False,packed_lookup=True)
            root_cfg=a.out/f'{case}-{seed}-root.json'
            root_cfg.write_text(json.dumps(dict(control='use',forbid_fallback=True,encoding='resident')))
            req['root_config']=str(root_cfg);assert not req['multi_residual'] and not read(Path(req['single_config']))['residual']
            with ExitStack() as stack:
                base=stack.enter_context(ref.session(a.vanilla/'vanilla',b/'program.json'))
                audit=stack.enter_context(ref.session(a.vanilla/'vanilla-audit',b/'program.json'))
                infer=stack.enter_context(ref.session(a.native,b/'program.json',b/'plans.json'))
                truth=audit(dict(audit=True));arms={'vanilla':dict(ms=[],runs=truth['runs'],rhs=truth['rhs_count'])}
                first=None
                for mode in a.modes:
                    v=infer(dict(req,audit=True,multi_mode=mode));q=ref.compare(v,truth)
                    assert q['aligned'] and q['neural_rhs']==truth['rhs_count'] and 100*q['direct_cells']>=98*q['fresh']
                    # Serial numbers of newly emitted packets may change when a proved-dead
                    # packet is eliminated. Compare the surviving full addresses, values,
                    # source ordinals, physical roots and dependent merge allocations independently.
                    q['multi_winners']=ref.digest([{k:v for k,v in t.items() if k!='local_token_id'} for t in v['multi']['tickets']])
                    q['root_evidence']=ref.digest([r[:2]+r[3:] for r in v['root_recipe']['commits']])
                    q['root_ids']=ref.digest([r[:5] for r in v['root_recipe']['fresh']])
                    q['nested_ids']=ref.digest([(r['allocated'],r['template'],r['parent']['ordinal']) for r in v['merge_child']['issued'] if r['allocated'] is not None])
                    signatures=dict((k,q[k]) for k in ('state_sha','cells','neural_rhs','fresh','direct_cells','rhs','multi_winners','root_evidence','root_ids','nested_ids'))
                    if 'guard' not in mode:signatures.update({k:q[k] for k in ('raw','wire_hash','commits','physical','multi','children')})
                    if first is None:first=signatures
                    else:assert all(x==first[k] for k,x in signatures.items()),(mode,case)
                    q.update(ms=[],pair=v['multi'].get('pair_stats'),delta=v['multi'].get('delta_stats'),counts=v['multi']['counts'],signature=v['multi'].get('signature_stats'))
                    arms[mode]=q
                    del v
                modes=list(arms)
                for trial in range(a.repeats+1):
                    i=trial%len(modes);order=modes[i:]+modes[:i]
                    for mode in order if trial%2 else order[::-1]:
                        got=base({}) if mode=='vanilla' else infer(dict(req,audit=False,multi_mode=mode))
                        assert got['state_sha']==truth['state_sha'] and got['runs']==truth['runs']
                        if mode!='vanilla':assert got['root_recipe']['allocated']==arms[mode]['root_allocated']
                        if trial:arms[mode]['ms'].append(got['ms'])
                for v in arms.values():v['median_ms']=median(v['ms'])
                report[f'{case}/{seed}']=arms
                (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
                print(case,seed,[(k,round(v['median_ms'],1)) for k,v in arms.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('native','vanilla','holdout','out'):p.add_argument(k,type=Path)
    p.add_argument('--tied-packed',action='store_true')
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d'])
    p.add_argument('--seeds',nargs='+',type=int,default=[1703])
    p.add_argument('--modes',nargs='+',default=['stackseal3xlearned','rowdeltapairdeltastackseal3xlearned'])
    p.add_argument('--repeats',type=int,default=6);run(p.parse_args())
