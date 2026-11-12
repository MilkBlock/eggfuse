"""Offline boundary-margin targets; dense polynomial ridge runtime unchanged."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from specialized import Adapter,score,ks,t,ROOT

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 base=dict(np.load(ROOT/'out/cell-ridge-kernel/compact/model.npz'));_,f,target,train,valid,test=t.dataset();base['degrees']=np.full(17,int(base['degree']));base['regs']=np.full(17,10.)
 m=Adapter(p=base);z=m.encode(f);src,a=np.where(train[:,None]&train[target]);dst=target[src,a];truth=f[dst][:,base['columns']];logs=[];best=None
 for gain in (.25,.5,1.):
  m=Adapter(p={k:v.copy() for k,v in base.items()})
  for iteration in range(13):
   val=score(m,z,f,target,valid);row=dict(gain=gain,iteration=iteration,validation=val);logs.append(row);print(row,flush=True);quality=(val['trace'],val['single'])
   if best is None or quality>best[0]:best=(quality,row);m.save(args.output/'model.npz')
   if iteration==12:break
   pred=m.step(z[src],a);raw=(pred*base['scale'])@base['basis'].T+base['mean']
   # Push only training rows that violate the .25/.75 confidence margin.
   correction=np.where(truth>.5,np.maximum(.75-raw,0),np.minimum(.25-raw,0))
   target_raw=truth+gain*correction
   y=((target_raw-base['mean'])@base['basis'])/base['scale']
   mm=ks.Model(base['centers'],int(base['degree']),base['bound']);mm.fit(z[src],a,y,10.)
   m.p['w']=np.stack([w for w,b in mm.bank]);m.p['bias']=np.stack([b for w,b in mm.bank])
 final=Adapter(args.output/'model.npz');result=dict(selection=best[1],validation=logs,test=score(final,z,f,target,test),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest());(args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('TEST',result['test'])
if __name__=='__main__':main()
