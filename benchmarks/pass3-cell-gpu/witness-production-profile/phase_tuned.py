"""Nested feature, scoring, seal and multi-parent clocks on the complete tuned stack."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'compact-recipes'))
from study import read, session


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    root=a.out/'roots.json'
    root.write_text(json.dumps(dict(control='use',forbid_fallback=True,encoding='checked_slots')))
    result={}
    for case in a.cases:
        b=a.bundles/f'{case}-1703';req=read(b/'request.json')
        for field in ('single_config','merge_config'):req[field]=str(b/req[field])
        req.update(archive_single_winners=a.archive,root_config=str(root),multi_weights=str(a.weights/f'{case}-1703-tied.json'),
                   baked_codes=str(a.weights/f'{case}-1703-tied.bin'),radius=0,packed_lookup=True,baked_row_index=False,
                   multi_mode='profilerowdeltapairguardstackseallearned',
                   rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,profile=True))
        samples=[]
        with session(a.native,b/'program.json',b/'plans.json') as call:
            for i in range(5):
                v=call(req)
                row=v['single']['adaptive_rows']
                assert row['stats']['emitted']>0
                assert len(row['phase_ns'])==4
                if not a.verifier_clock and row['phase_ns'][3]!=0:raise RuntimeError('enable the observed single verifier clock')
                if a.verifier_clock and row['phase_ns'][3]<=0:raise RuntimeError('expected active single verifier clock')
                simple=[x/1e6 for x in row['phase_ns'][:4 if a.verifier_clock else 3]]
                multi=[sum(r[key] for r in v['multi']['rule_profile']) for key in ('frame_ms','issuance_ms','validation_ms')]
                if i:samples.append([v['ms'],*simple,*multi])
        result[case]=dict(state_sha=v['state_sha'],runs=v['runs'],samples_ms=samples,
                           median_ms=dict(zip(['execute','single_headers_features','single_policy_score','single_tokens_seal']+(['single_verify_attach'] if a.verifier_clock else [])+[
                                               'multi_frames','multi_issue_seal','multi_verify'],map(median,zip(*samples)))))
        (a.out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(case,result[case]['median_ms'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('native','bundles','weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['jacobi-1d','conjugate-gradient'])
    p.add_argument('--archive',action='store_true')
    p.add_argument('--verifier-clock',action='store_true')
    run(p.parse_args())
