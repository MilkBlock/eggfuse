"""Estimate work-weighted payoff of frozen libraries after the holdouts have been evaluated."""
import argparse,json
from math import fsum
from statistics import median
from pathlib import Path
from train import capture


def returns(events,policies):
    report={}
    for case,shapes in events.items():
        gain={k:median(a-b for a,b in zip(v['original'],v['expanded'])) for k,v in shapes.items()}
        available=fsum(max(d,0.) for d in gain.values())
        arms={}
        for label,spec in policies.items():
            if label.endswith('1709'):continue
            selected=set(spec['members'])
            ds=[v for k,v in gain.items() if k in selected]
            pos=fsum(max(0.,v) for v in ds);cost=-fsum(min(0.,v) for v in ds)
            arms[label]=dict(active_shapes=len(ds),positive_ms=pos,harm_ms=cost,net_ms=pos-cost,
                             work_weighted_coverage=pos/available if available else None)
        report[case]=dict(observed_shapes=len(gain),positive_opportunity_ms=available,policies=arms)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','learning','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;a.repeats=3
    a.out.mkdir(parents=True,exist_ok=False)
    events=capture(a,set(),('conjugate-gradient','3mm'))
    (a.out/'heldout-costs.json').write_text(json.dumps(events,separators=(',',':'))+'\n')
    if not a.learning.exists():
        print('Archived paired held-out costs. Compute weighted returns after the donor fit is available.')
        raise SystemExit(0)
    policies=json.loads(a.learning.read_bytes())['policies']
    v=returns(events,policies);(a.out/'weighted.json').write_text(json.dumps(v,indent=1)+'\n')
    print([(k,round(r['positive_opportunity_ms'],2),round(r['policies']['iterated']['net_ms'],2)) for k,r in v.items()])
