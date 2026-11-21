"""Calibrate independent score thresholds and a non-neural per-site Bake frequency table on donors."""
import argparse,json,math
from collections import defaultdict
from pathlib import Path

def cutoff(mass):
    target=sum(mass.values())/4
    for rank in sorted(mass,reverse=True):
        if mass[rank]>=target:return dict(rank=rank,tie=target/mass[rank])
        target-=mass[rank]
    raise ValueError('donor has no admissible sites')


def freeze(donors,model):
    assert set(donors)=={'sum-bits','dot-product','jacobi-1d'}
    rows=[r['arms']['all'] for r in donors.values()]
    groups=[(x,b) for r in rows for x,b in r['features'] if b['admissible']]
    rates=defaultdict(lambda:[0,0,0])
    for r in rows:
        for site,v in r['sites']:
            key=tuple(site)
            for i,j in enumerate((5,3,6)):rates[key][i]+=v[j]
    result={}
    for mode in ('uniform','static','local-first','baked-hits','baked-readers','learned-hits','learned-readers'):
        rank=lambda z:math.floor(z*1e6+.5)
        masses=defaultdict(int)
        spec=dict(percent=25,mode=mode)
        if mode.startswith('baked'):
            target=1 if mode=='baked-hits' else 2
            avg=sum(r[target] for r in rates.values())/sum(r[0] for r in rates.values())
            sites=[]
            for (rule,op),r in sorted(rates.items()):
                # Eight opportunities of prior mass prevent zero-count sites from having spurious confidence.
                estimate=(r[target]+8*avg)/(r[0]+8)
                sites.append([rule,op,estimate]);masses[rank(estimate)]+=r[0]
            spec.update(mode='baked-sites',sites=sites,default_score=avg)
        else:
            for x,b in groups:
                if mode=='uniform':score=0.
                elif mode=='static':score=x[0]+x[1]+.5*(x[10]+x[11])
                elif mode=='local-first':score=2*int(x[10]+x[11]>0)+.5*(x[0]+x[1])
                else:
                    w=model[mode]['weights']
                    score=max(w[i*13+12]+sum(m*v for m,v in zip(w[i*13:i*13+12],x))
                              for i in (0,1) if x[i] or x[10+i])
                    spec.update(mode='model',weights=w)
                masses[rank(score)]+=b['admissible']
        spec['global_cut']=cutoff(masses);result[mode]=spec
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('donors','model','out'):p.add_argument(k,type=Path)
    a=p.parse_args();res=freeze(json.loads(a.donors.read_bytes()),json.loads(a.model.read_bytes()))
    a.out.write_text(json.dumps(res,indent=1)+'\n')
