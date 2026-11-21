"""Fresh-process inference-window RSS, calibrated independently against the same default CPU."""
from argparse import ArgumentParser
from pathlib import Path
from runpy import run_path
from statistics import median
import json
HERE=Path(__file__).resolve().parent
probe=run_path(str(HERE.parent/'verified-wave-rss/measure.py'))
driver=run_path(str(HERE/'study.py'))
def main():
    p=ArgumentParser()
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;a.cap=8192;a.out.mkdir(parents=True,exist_ok=False)
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes());a.fraction=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())['models']['fraction']
    out={}
    for case in ('sum-bits','3mm'):
        program,plans,req=driver['src'].common.config(a,case)
        cfg=driver['wave']['settings'](req,a)['packed']
        vanilla=a.exp/'verified-wave-rss-native-v1/vanilla'
        cal=[probe['run'](vanilla,[program],{},True) for _ in range(3)]
        base=median(x['trace'][0][1] for x in cal);growth=median(max(t[1] for t in x['trace'])-x['trace'][0][1] for x in cal)
        caps={str(f):round(growth*f) for f in (.5,.9)}
        dest=dict(calibration_entry_kib=base,calibration_growth_kib=growth,threshold_growth_kib=caps,reference=cal[0]['state_sha'],rows={})
        modes={'ordinary':dict(cfg),'dual':dict(cfg,strict_dual=driver['template'])}
        for i in range(4):
            for j,n in enumerate(modes if i%2 else reversed(modes)):
                trace={}
                for sample in ([True,False] if (i+list(modes).index(n))%2 else [False,True]):
                    v=probe['run'](a.native,[program,plans],modes[n],sample)
                    assert v['state_sha']==cal[0]['state_sha'] and v['runs']==cal[0]['runs']
                    trace['sample_ms' if sample else 'plain_ms']=v['ms']
                    if sample:
                        t=v['trace'];trace.update(entry_kib=t[0][1],peak_kib=max(o[1] for o in t),rise_kib=max(o[1] for o in t)-t[0][1],samples=len(t))
                        trace['t_growth_ms']={k:next((o[0]/1000 for o in t if o[1]-t[0][1]>=target),None) for k,target in caps.items()}
                        trace['t_absolute_ms']={k:('left' if t[0][1]>=base+target else next((o[0]/1000 for o in t if o[1]>=base+target),None)) for k,target in caps.items()}
                        trace['trace_kib']=[[o[0],o[1]] for o in t]
                dest['rows'].setdefault(n,[]).append(trace)
        out[case]=dest;(a.out/'rss.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
        print(case,caps,[(n,[r['t_growth_ms']['0.9'] for r in rs]) for n,rs in dest['rows'].items()],flush=True)
if __name__=='__main__':main()
