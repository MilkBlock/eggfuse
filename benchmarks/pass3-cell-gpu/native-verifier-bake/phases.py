"""Separate native single-source verification/assembly clocks from uninstrumented wall timings."""
import argparse,importlib.util,json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('native_check_settings',HERE/'study.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)


def profile(a):
    a.out.mkdir(parents=True,exist_ok=False);data={}
    for case in a.cases:
        program,plans,req=entry.base.common.config(a,case);arms=entry.settings(req,a)
        names=['off','projected','all'];timings={k:[] for k in names}
        with entry.base.base.session(a.exp/'compact-vanilla-20261121/vanilla',program) as exact:
            gold=exact({})
        with entry.base.base.session(a.native,program,plans) as infer:
            for i in range(4):
                for name in names[i%3:]+names[:i%3]:
                    cfg=arms[name];v=infer(dict(cfg,rows=dict(cfg['rows'],profile=True)))
                    assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs'] and v['multi']['total_rhs']==gold['rhs_count']
                    phase=v['single']['adaptive_rows']['phase_ns'][3]/1e6
                    assert 0<phase<v['ms']
                    if i:timings[name].append(dict(check_and_assemble_ms=phase,inference_ms=v['ms']))
        data[case]=timings
        (a.out/'phases.json').write_text(json.dumps(data,indent=1)+'\n')
        print(case,[(k,round(median(s['check_and_assemble_ms'] for s in v),2)) for k,v in timings.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    a=p.parse_args();a.seed=1703;profile(a)
