"""Calibrate the emission rate on training programs alone, preserving an explicit recall target."""
import argparse,json
from pathlib import Path
import numpy as np
from train import CASES

def prepare(report,model):
    d=json.loads(report.read_bytes())['single_witness'];f=np.asarray(d['features'],np.float32)/32
    hidden=f@np.array(model['x'],np.float32).T+np.array(model['b'],np.float32)
    events=[]
    for rid,n,group in d['events']:
        idx=np.array([v[0] for v in group]);c=np.array([v[1] for v in group],np.float32);tot=c.sum(1)
        events.append((rid,n,hidden[idx],tot,c[:,1],float(tot@f[idx,5]/n)))
    return events
def rollout(events,m,threshold):
    H=np.array(m['h'],np.float32);out=np.array(m['out'],np.float32);rb=np.array(m['rbias'],np.float32)
    U=np.array(m['recurrent'],np.float32);T=np.array(m['update'],np.float32);h=np.zeros(4,np.float32)
    total=selected=positives=won=0
    for rid,n,hidden,counts,true,fresh in events:
        score=np.tanh(hidden+h@H.T)@out+m['bias']+m['rules'][rid%64]
        mask=score>=threshold;b=float(counts@mask)
        h=np.tanh(U@h+T@np.asarray([min(n,128)/128,b/n,fresh,(rid%64)/63],np.float32)+rb)
        total+=n;selected+=int(b);positives+=int(true.sum());won+=int(true@mask)
    return dict(total=total,emitted=selected,positives=positives,hits=won)
def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    for seed in (1703,1709):
        m=json.loads((Path(str(a.weights).replace('SEED',str(seed)))/'config.json').read_bytes())['model']
        corp={n:prepare(a.capture/n/'report.json',m) for n in CASES}
        rows=[]
        for cutoff in np.arange(-5.,2.01,.125):
            stats={n:rollout(d,m,float(cutoff)) for n,d in corp.items()}
            rows.append((float(cutoff),stats))
        for name,target in [('high',.99),('balanced',.97),('coverage',.95)]:
            eligible=[(t,r) for t,r in rows if all(v['hits']>=target*v['positives'] for v in r.values())]
            t,s=min(eligible,key=lambda tr:(sum(v['emitted'] for v in tr[1].values()),-tr[0]))
            d=dict(mode='learned',residual=True,model={**m,'threshold':t})
            (a.out/f'{seed}-{name}.json').write_text(json.dumps(d,separators=(',',':'))+'\n')
            print(seed,name,t,[(v['emitted'],v['total'],v['hits'],v['positives']) for v in s.values()],flush=True)
        (a.out/f'calibration-{seed}.json').write_text(json.dumps(rows,separators=(',',':'))+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('weights',type=Path);p.add_argument('out',type=Path)
    main(p.parse_args())
