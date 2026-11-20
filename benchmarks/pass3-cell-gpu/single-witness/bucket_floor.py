"""Choose conservative score floors per trained rule embedding on train families without any test labels."""
import argparse,json
from pathlib import Path
import numpy as np
from calibrate import prepare
from train import CASES


def scan(seq,m,cutoffs):
    H=np.asarray(m['h'],np.float32);out=np.asarray(m['out'],np.float32);rb=np.asarray(m['rbias'],np.float32)
    U=np.asarray(m['recurrent'],np.float32);T=np.asarray(m['update'],np.float32);h=np.zeros(4,np.float32)
    minimum=np.full(64,np.inf);total=sent=pos=won=0
    for rid,n,hidden,c,y,fresh in seq:
        b=rid%64
        score=np.tanh(hidden+h@H.T)@out+m['bias']+m['rules'][b]
        mask=score>=cutoffs[b];count=int(c@mask)
        positive=score[y>0]
        if len(positive):minimum[b]=min(minimum[b],float(positive.min()))
        h=np.tanh(U@h+T@np.array([min(n,128)/128,count/n,fresh,b/63],np.float32)+rb)
        total+=n;sent+=count;pos+=int(y.sum());won+=int(y@mask)
    return minimum,dict(total=total,sent=sent,positives=pos,hits=won)


def calibrate(a):
    a.out.mkdir(parents=True,exist_ok=False)
    for seed in (1703,1709):
        m=json.loads((a.models/f'{seed}-high.json').read_bytes())['model']
        train={n:prepare(a.captures/n/'report.json',m) for n in CASES}
        floor=np.full(64,np.inf)
        for original in (-6.,-3.5,-2.5,-1.,1.):
            for seq in train.values():
                lower,_=scan(seq,m,np.full(64,original));floor=np.minimum(floor,lower)
        floor[~np.isfinite(floor)]=-16.
        for margin in (.125,.5,1.0):
            cutoff=floor-margin
            for _ in range(4):
                observed={};revised=cutoff.copy()
                for n,seq in train.items():
                    lower,observed[n]=scan(seq,m,cutoff);revised=np.minimum(revised,lower-margin)
                if all(v['hits']==v['positives'] for v in observed.values()):break
                cutoff=revised
            assert all(v['hits']==v['positives'] for v in observed.values())
            calibrated={**m,'rules':(np.array(m['rules'])-cutoff).astype(np.float32).tolist(),'threshold':0.}
            label=f'{seed}-bucket-{margin}'
            (a.out/f'{label}.json').write_text(json.dumps(dict(mode='learned',residual=True,model=calibrated),separators=(',',':')))
            (a.out/f'{label}-train.json').write_text(json.dumps(dict(train=observed,margin=margin,floors=cutoff.tolist()),separators=(',',':')))
            print(label,sum(v['sent'] for v in observed.values()),sum(v['total'] for v in observed.values()),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('captures',type=Path);p.add_argument('models',type=Path);p.add_argument('out',type=Path)
    calibrate(p.parse_args())
