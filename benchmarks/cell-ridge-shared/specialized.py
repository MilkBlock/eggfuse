"""Validation-selected per-action continuous polynomial ridge banks."""
import argparse,importlib.util,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('ks',ROOT/'benchmarks/cell-ridge-kernel/study.py');ks=importlib.util.module_from_spec(spec);spec.loader.exec_module(ks);t=ks.t
class Adapter:
 def __init__(self,path=None,p=None):self.p=dict(np.load(path)) if path else p
 def encode(self,f):
  p=self.p;return ((f[:,p['columns']]-p['mean'])@p['basis'])/p['scale']
 def decode(self,z):
  p=self.p;f=np.concatenate([z,(1+z@p['centers'].T/17)**int(p['readout_degree'])],1);return f@p['decoder_w']+p['decoder_b']
 def step(self,z,a):
  p=self.p;out=z.copy()
  for degree in np.unique(p['degrees']):
   take=np.flatnonzero(np.isin(a,np.flatnonzero(p['degrees']==degree)));zz=z[take];f=np.concatenate([zz,(1+zz@p['centers'].T/17)**degree],1)
   for action in np.unique(a[take]):
    mask=a[take]==action;out[take[mask]]+=f[mask]@p['w'][action]+p['bias'][action]
  return np.clip(out,-p['bound'],p['bound'])
 def save(self,path):np.savez(path,**self.p)
def load_adapter(path):return Adapter(path)
def score(m,z,f,target,mask):
 ids=np.repeat(np.flatnonzero(mask),17);a=np.tile(np.arange(17),mask.sum());single=((m.decode(m.step(z[ids],a))>=.5)==f[target[ids,a]]).all(1).mean()
 ids=np.tile(np.flatnonzero(mask),4);cur=z[ids].copy();ok=np.ones(len(ids),bool);events=np.random.default_rng(17).integers(0,17,(12,len(ids)));events[2]=15;events[5]=16;events[8]=events[7]
 for a in events:cur=m.step(cur,a);ids=target[ids,a];out=m.decode(cur);ok&=np.isfinite(out).all(1)&((out>=.5)==f[ids]).all(1)
 return dict(single=float(single),trace=float(ok.mean()))
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 base=dict(np.load(ROOT/'out/cell-ridge-kernel/compact/model.npz'));_,f,target,train,valid,test=t.dataset();temp=Adapter(p=base);z=temp.encode(f);src,a=np.where(train[:,None]&train[target]);dst=target[src,a];vid=np.flatnonzero(valid)
 choices=[[] for _ in range(17)];logs=[]
 for degree in (2,3,4,5):
  for reg in (.001,.1,10.):
   m=ks.Model(base['centers'],degree,base['bound']);m.fit(z[src],a,z[dst],reg)
   for action in range(17):
    pred=m.step(z[vid],np.full(len(vid),action));dest=target[vid,action];full=((temp.decode(pred)>=.5)==f[dest]).all(1).mean();raw=(pred*base['scale'])@base['basis'].T+base['mean'];boundary=((raw>=.5)==f[dest][:,base['columns']]).all(1).mean();rmse=np.mean((pred-z[dest])**2)
    row=dict(action=action,degree=degree,reg=reg,full=float(full),boundary=float(boundary),mse=float(rmse));logs.append(row);choices[action].append((row,m.bank[action]))
 best=None;combo=[]
 for metric in ('full','boundary'):
  selected=[max(items,key=lambda item:(item[0][metric],-item[0]['mse'])) for items in choices];params=dict(base,degrees=np.array([r['degree'] for r,b in selected]),regs=np.array([r['reg'] for r,b in selected]),w=np.stack([b[0] for r,b in selected]),bias=np.stack([b[1] for r,b in selected]));m=Adapter(p=params)
  rng=np.random.default_rng(441);allowed=[np.flatnonzero(train[target[i]]) for i in range(len(z))];second=np.array([rng.choice(allowed[i]) for i in dst]);end=target[dst,second];ok=train[target[src,second]]
  for iteration in range(7):
   val=score(m,z,f,target,valid);row=dict(metric=metric,iteration=iteration,validation=val,selected=[r for r,b in selected]);combo.append(row);print(metric,iteration,val,flush=True);quality=(val['trace'],val['single'])
   if best is None or quality>best[0]:best=(quality,row);m.save(args.output/'model.npz')
   if iteration==6:break
   pred=m.step(z[src],a);other=m.step(z[src[ok]],second[ok]);xx=np.concatenate([z[src],pred,pred,other]);aa=np.concatenate([a,a,second,a[ok]]);yy=np.concatenate([z[dst],z[dst],z[end],z[end[ok]]])
   for action in range(17):
    take=aa==action;mm=ks.Model(base['centers'],int(m.p['degrees'][action]),base['bound']);features=mm.features(xx[take]);mx=features.mean(0);scale=np.maximum(features.std(0),.05);res=(yy-xx)[take];my=res.mean(0);xc=(features-mx)/scale;yc=res-my;w=np.linalg.solve(xc.T@xc+m.p['regs'][action]*np.eye(xc.shape[1]),xc.T@yc)/scale[:,None];m.p['w'][action]=w;m.p['bias'][action]=my-mx@w
 final=Adapter(args.output/'model.npz');result=dict(selection=best[1],screen=logs,combinations=combo,test=score(final,z,f,target,test),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest());(args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('TEST',result['test'])
if __name__=='__main__':main()
