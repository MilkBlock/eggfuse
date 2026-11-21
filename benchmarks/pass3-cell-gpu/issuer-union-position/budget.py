"""Trace-backed transfer of donor-frozen feature thresholds, preserving the live union dynamics.

The native tags are passive. Outcomes for an entire pre-issue feature group are observed even if
that particular capped live policy declined some of the group. Fractional tie acceptance below
is an expectation under independent randomization, not a new deployed native decision.
"""
from collections import defaultdict
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def score(name,x,weights):
    if name=='uniform':return 0.
    if name=='static':return x[0]+x[1]+.5*(x[10]+x[11])
    ws=weights[name]['weights']
    return max(ws[i*13+12]+sum(a*b for a,b in zip(ws[i*13:i*13+12],x))
               for i in (0,1) if x[i] or x[10+i])


def threshold(name,donor,weights):
    masses=defaultdict(int)
    for source in donor.values():
        for x,b in source['arms']['all']['features']:
            n=b['admissible']
            if n:masses[score(name,x,weights)]+=n
    target=sum(masses.values())/4
    remaining=target
    for v in sorted(masses,reverse=True):
        if masses[v]>=remaining:return {'threshold':v,'tie_probability':remaining/masses[v],'training_budget':target}
        remaining-=masses[v]
    raise ValueError('no training offers')


def compute(folder):
    read=lambda f:json.loads((folder/f).read_bytes())
    donor,test,weights=read('donors.json'),read('heldout.json'),read('model.json')
    kinds=('uniform','static','learned-hits','learned-readers')
    cuts={k:threshold(k,donor,weights) for k in kinds}
    data={}
    for n,source in test.items():
        choices={}
        for k in kinds:
            cut=cuts[k];half=source['arms'][k];counts=[0.,0.,0.]
            for x,b in half['features']:
                if not b['admissible']:continue
                v=score(k,x,weights)
                prob=(1. if v>cut['threshold'] else cut['tie_probability'] if v==cut['threshold'] else 0.)
                counts[0]+=prob*b['admissible'];counts[1]+=prob*b['displaced_valid'];counts[2]+=prob*b['valid_readers']
            choices[k]=dict(zip(('expected_hints','expected_correct','expected_readers'),counts))
        data[n]=choices
    return dict(training=cuts,heldout=data)


if __name__=='__main__':
    (HERE/'thresholds.json').write_text(json.dumps(compute(HERE),indent=1)+'\n')
