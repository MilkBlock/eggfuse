"""Capture prospective graph observations separately from post-Run source labels."""
import argparse,sys,json
from pathlib import Path
import numpy as np
from catalog import read,load_catalog
GPU=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(GPU))
from run import execute

def inputs(corpus,ref,n):
    if n in ('sum-bits','dot-product'):
        return ref/f'release-input-{n}',ref/n/'program.json',ref/f'release-{n}'
    return corpus/n/'input',corpus/n/'program.json',corpus/n/'device'

def verify(dest,gold,image):
    with np.load(dest/'output.npz') as now,np.load(gold/'output.npz') as old:
        for k in ('runs','resumes','writes','parents','unions','meta'):
            np.testing.assert_array_equal(now[k],old[k],err_msg=k)
        np.testing.assert_array_equal(now['rhs'][:,:2],old['rhs'][:,:2])
        np.testing.assert_array_equal(now['rhs'][:,4:],old['rhs'][:,4:])
        for i,t in enumerate(read(image/'ingress.json')['tables']):
            at=now['meta'][:,0]==i;w=len(t['schema'])
            np.testing.assert_array_equal(now['rows'][at,:w],old['rows'][at,:w])

def capture(corpus,ref,weights,out):
    out.mkdir(parents=True,exist_ok=False)
    report={}
    for n,case in read(corpus/'collection.json').items():
        image,p,gold=inputs(corpus,ref,n)
        cat=load_catalog(image,p,ref/'sum-bits/program.json')
        dest=out/n; ranks=8
        execute(image/'device.json',weights,ref/'ports-1703.pt',2048,2,dest,
                neural=dict(catalog=cat,rows=2,ranks=ranks,hidden=8,capture=True))
        verify(dest,gold,image)
        with np.load(dest/'neural-inputs.npz') as obs,np.load(dest/'output.npz') as z:
            f=obs['features'];base=z['rhs'];piv=obs['pivot']
            positive=np.zeros(f.shape[:2],np.bool_)
            lookup={(rid,p):leaf for leaf,(rid,p,_,_) in enumerate(cat) if rid>=0}
            eligible=0
            for token,pivot in zip(base,piv):
                t=int(token[0])-1; leaf=lookup.get((int(token[1]),int(pivot)-1))
                if leaf is None:continue
                eligible+=1
                idx=np.flatnonzero(f[t,leaf*ranks:(leaf+1)*ranks,0]==int(token[3]))
                if len(idx):positive[t,leaf*ranks+idx]=True
            np.savez_compressed(dest/'training.npz',features=f,positive=positive)
            report[n]=dict(split=case['split'],runs=len(f),all_rhs=len(base),eligible=eligible,
                           presented=int((f[:,:,0]>=0).sum()),positive=int(positive.sum()),
                           positive_runs=int(positive.any(1).sum()),two_slot_upper=int(np.minimum(2,positive.sum(1)).sum()),
                           admitted_leaves=sum(r[0]>=0 for r in cat))
        print(n,report[n],flush=True);(out/'summary.json').write_text(json.dumps(report,indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('corpus','ref','weights','out'):p.add_argument(k,type=Path)
    a=p.parse_args();capture(a.corpus,a.ref,a.weights,a.out)
