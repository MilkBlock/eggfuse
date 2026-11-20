"""Instrument reverse activation and its nested directory interval separately from paired wall time."""
import argparse,importlib.util,json
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('phase_config',HERE/'study.py')
entry=importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def phases(a):
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for case in a.cases:
        p,plans,req=entry.bridge.config(a,case)
        configs=entry.configure(req,a)
        with entry.bridge.parent.base.session(a.exp/'compact-vanilla-20261121/vanilla',p) as ref:
            gold=ref({})
        names=['offset','rebuild','delta','union']
        samples={k:[] for k in names}
        with entry.bridge.parent.base.session(a.native,p,plans) as infer:
            for i in range(4):
                for key in names[i:]+names[:i]:
                    r=configs[key]
                    v=infer(dict(r,multi_mode='profile'+r['multi_mode']))
                    assert v['state_sha']==gold['state_sha'] and v['multi']['total_rhs']==gold['rhs_count'] and v['runs']==gold['runs']
                    w=v['multi']['patch_ports'];assert 0<w['directory_ns']<=w['activation_ns'] and w['audit_rows']==0
                    if i:samples[key].append(dict(directory_ms=w['directory_ns']/1e6,activation_ms=w['activation_ns']/1e6,inference_ms=v['ms']))
        report[case]=samples
        (a.out/'phases.json').write_text(json.dumps(report,indent=1)+'\n')
        print(case,[(k,round(median(x['directory_ms'] for x in v),2),round(median(x['activation_ms'] for x in v),2)) for k,v in samples.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    a=p.parse_args();a.seed=1703;a.lost_log=False;phases(a)
