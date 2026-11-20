"""Per-rule counters and wall time around snapshot acquisition, proposal generation/seal and verification."""
import argparse
import json
from pathlib import Path
from statistics import median
from holdout import ref


def profile(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    for case in a.cases:
        b=a.bundles/f'{case}-1703';req=ref.read(b/'request.json')
        for k in ('single_config','multi_weights','merge_config','root_config'):req[k]=str(b/req[k])
        r=a.out/f'{case}-root.json';r.write_text(json.dumps(dict(control='use',encoding='resident',forbid_fallback=True)))
        req.update(root_config=str(r),audit=False,multi_mode='profile'+a.mode)
        if a.tied:
            req.update(multi_weights=str(a.tied/f'{case}-1703-tied.json'),baked_codes=str(a.tied/f'{case}-1703-tied.bin'),
                       packed_lookup=True,baked_row_index=False,radius=0)
        with ref.session(a.binary,b/'program.json',b/'plans.json') as call:
            samples=[]
            for trial in range(5):
                v=call(req)
                if 'source_error' in v:raise RuntimeError(v['source_error'])
                if trial:samples.append(v)
            def series(k):
                return median(sum(r[k] for r in s['multi']['rule_profile']) for s in samples)
            g=v['multi']['rule_profile'];res={}
            for rid,r in enumerate(g):
                if r['calls']:
                    res[rid]={k:median(s['multi']['rule_profile'][rid][k] for s in samples) for k in r}
            results[case]=dict(full_ms=median(s['ms'] for s in samples),phases={k:series(k) for k in ('frame_ms','issuance_ms','validation_ms')},rules=res)
        (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
        t=results[case];print(case,t['full_ms'],t['phases'],sorted(t['rules'],key=lambda i:-t['rules'][i]['issuance_ms'])[:8],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','bundles','out'):p.add_argument(k,type=Path)
    p.add_argument('--mode',default='rowdeltapairguardstackseallearned')
    p.add_argument('--tied',type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    profile(p.parse_args())
