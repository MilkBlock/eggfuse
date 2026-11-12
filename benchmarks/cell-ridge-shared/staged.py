"""Two learned continuous stages with additional train-apply intermediate supervision."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from specialized import Adapter as Prior,ks,t,ROOT

def ridge(x,y,reg):
 x=x.astype(np.float64);y=y.astype(np.float64);mx=x.mean(0);my=y.mean(0);s=np.maximum(x.std(0),.05);xx=(x-mx)/s;yy=y-my
 w=np.linalg.solve(xx.T@xx+reg*np.eye(xx.shape[1]),xx.T@yy)/s[:,None]
 return w.astype(np.float32),(my-mx@w).astype(np.float32)
class Adapter(Prior):
 def step(self,z,a):
  p=self.p;out=super().step(z,a);phi=np.concatenate([out,(1+out@p['closure_centers'].T/17)**int(p['closure_degree'])],1)
  return np.clip(out+phi@p['closure_w']+p['closure_b'],-p['bound'],p['bound'])
def load_adapter(path):return Adapter(path)
def score(m,z,f,target,mask):
 ids=np.repeat(np.flatnonzero(mask),17);a=np.tile(np.arange(17),mask.sum());single=((m.decode(m.step(z[ids],a))>=.5)==f[target[ids,a]]).all(1).mean()
 ids=np.tile(np.flatnonzero(mask),4);cur=z[ids].copy();ok=np.ones(len(ids),bool);events=np.random.default_rng(17).integers(0,17,(12,len(ids)));events[2]=15;events[5]=16;events[8]=events[7]
 for a in events:cur=m.step(cur,a);ids=target[ids,a];out=m.decode(cur);ok&=np.isfinite(out).all(1)&((out>=.5)==f[ids]).all(1)
 return dict(single=float(single),trace=float(ok.mean()))
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 base=dict(np.load(ROOT/'out/cell-ridge-kernel/compact/model.npz'));states,f,target,train,valid,test=t.dataset();temp=Prior(p=base);z=temp.encode(f);src,a=np.where(train[:,None]&train[target]);dst=target[src,a]
 raw=[]
 for source,action in zip(src,a):
  partition,flags=states[source];part=list(partition[:6])
  if action<15:
   i,j=t.BASE_PAIRS[action];x,y=part[i],part[j];part=[x if v==y else v for v in part]
  else:flags|=1<<(action-15)
  raw.append([int(part[i]==part[j]) for i,j in t.BASE_PAIRS]+[flags&1,(flags>>1)&1])
 raw=np.array(raw,dtype=np.float32);middle=((raw-base['mean'])@base['basis'])/base['scale'];unique=np.unique(middle,axis=0);logs=[];best=None
 # Stage two sees only admitted training apply intermediates and final train labels.
 for degree1 in (2,3):
  for reg1 in (.001,.1):
   first=ks.Model(base['centers'],degree1,base['bound']);first.fit(z[src],a,middle,reg1);pred=first.step(z[src],a)
   for degree2 in (3,5):
    for reg2 in (.001,.1,10.):
     for use_pred in (False,True):
      xx=np.concatenate([middle,pred]) if use_pred else middle;yy=np.concatenate([z[dst],z[dst]]) if use_pred else z[dst]
      phi=np.concatenate([xx,(1+xx@unique.T/17)**degree2],1);w,b=ridge(phi,yy-xx,reg2)
      params=dict(base,degrees=np.full(17,degree1),w=np.stack([v[0] for v in first.bank]),bias=np.stack([v[1] for v in first.bank]),closure_centers=unique,closure_degree=degree2,closure_w=w,closure_b=b)
      m=Adapter(p=params);val=score(m,z,f,target,valid);row=dict(degree1=degree1,reg1=reg1,degree2=degree2,reg2=reg2,predicted_training=use_pred,validation=val);logs.append(row);print(row,flush=True);quality=(val['trace'],val['single'])
      if best is None or quality>best[0]:best=(quality,row);m.save(args.output/'model.npz')
 final=Adapter(args.output/'model.npz');result=dict(selection=best[1],validation=logs,test=score(final,z,f,target,test),train_edges=len(src),unique_intermediates=len(unique),extra_supervision='Unclosed action intermediate from admitted training source only; closed labels restricted to train',source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest());(args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('TEST',result['test'])
if __name__=='__main__':main()
