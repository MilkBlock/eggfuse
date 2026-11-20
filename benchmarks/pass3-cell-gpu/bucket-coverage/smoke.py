import argparse,json,sys
from pathlib import Path
import numpy as np
from adapter import specialize,HERE
sys.path.insert(0,str(HERE.parent/'recurrent-generator'))
from capture import inputs,load_catalog,read,verify
from provenance import validate

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('corpus','ref','reader','out'):p.add_argument(k,type=Path)
    p.add_argument('--case',default='sum-bits');p.add_argument('--panel',default='partial');p.add_argument('--mode',default='range')
    a=p.parse_args()
    image,prog,gold=inputs(a.corpus,a.ref,a.case)
    cat=load_catalog(image,prog,a.ref/'sum-bits/program.json')
    checkpoint=read(HERE.parent/'recurrent-generator/receipts/actor-1703-2.json')
    fn=specialize(image,cat,a.panel,a.mode)
    cfg=dict(catalog=cat,rows=2,hidden=8,ranks=8,waves=2,feedback=2,receipt_head=True,close=False,weights=checkpoint['weights'])
    fn(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,a.out,neural=cfg,count_work=True)
    verify(a.out,gold,image)
    print('neural committed',validate(a.out,cat),flush=True)
    with np.load(a.out/'buckets.npz') as z:
        print(z['log'].sum((0,1)),z['stats'],(z['bank'][:,:,4]>0).sum(),flush=True)
