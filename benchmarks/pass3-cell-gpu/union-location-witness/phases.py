"""Time location issuance and verification separately from the ordinary full inference samples."""
import argparse,importlib.util,json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('location_options',HERE/'study.py')
trial=importlib.util.module_from_spec(s);s.loader.exec_module(trial)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','weights','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;a.arms=['static','strict','combined','baked'];a.model=json.loads(a.weights.read_bytes())
    a.out.mkdir(parents=True,exist_ok=False);result={}
    for case in ('conjugate-gradient','3mm'):
        prog,plans,req=trial.source.common.config(a,case);options=trial.choices(req,a)
        with trial.source.base.session(a.exp/'compact-vanilla-20261121/vanilla',prog) as ref:gold=ref({})
        samples={k:[] for k in a.arms}
        with trial.source.base.session(a.native,prog,plans) as infer:
            for i in range(4):
                for k in a.arms[i:]+a.arms[:i]:
                    v=options[k];out=infer(dict(v,union_locator=dict(v['union_locator'],profile=True)))
                    assert out['state_sha']==gold['state_sha'] and out['multi']['total_rhs']==gold['rhs_count'] and out['runs']==gold['runs']
                    w=out['union_locator']['stats']
                    assert not w['audits'] and w['issue_ns']>0 and w['verify_ns']>0
                    if i:samples[k].append({f:w[f]/1e6 for f in ('issue_ns','verify_ns','dispatch_patch_ns')})
        result[case]=samples;(a.out/'phases.json').write_text(json.dumps(result,indent=1)+'\n')
        print(case,[(k,round(median(x['issue_ns'] for x in v),2),round(median(x['verify_ns'] for x in v),2)) for k,v in samples.items()],flush=True)
