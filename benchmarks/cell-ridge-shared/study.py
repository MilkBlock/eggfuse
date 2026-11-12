"""Shared dense event/state kernel ridge, finite teacher only."""
import argparse,importlib.util,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('teacher',ROOT/'benchmarks/cell-real-state/study.py');t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
class Model:
 def features(self,z,a):
  x=np.concatenate([z,self.codes[a]],1)
  return np.concatenate([x,(1+x@self.centers.T/x.shape[1])**3],1)
 def fit(self,z,a,y,reg):
  f=self.features(z,a);s=np.maximum(f.std(0),.05);w,b=t.ridge(f/s,y-z,reg);self.w=(w/s[:,None]).astype(np.float32);self.b=b
 def step(self,z,a):return np.clip(z+t.predict(self.features(z,a),(self.w,self.b)),-self.bound,self.bound).astype(np.float16).astype(np.float32)
 def save(self,path):np.savez(path,**self.__dict__)
 def encode(self,f):return (((f-self.mean)@self.basis)/self.scale).astype(np.float16).astype(np.float32)
 def decode(self,z):return t.predict(z,(self.dw,self.db))
def load_adapter(path):
 m=Model();m.__dict__.update(dict(np.load(path)));return m
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 _,f,target,train,valid,test=t.dataset();mean=f[train].mean(0);_,_,vt=np.linalg.svd(f[train]-mean,full_matrices=False);basis=vt[:35].T;scale=np.maximum(((f[train]-mean)@basis).std(0),.1);z=(((f-mean)@basis)/scale).astype(np.float16).astype(np.float32);decoder=t.ridge(z[train],f[train],.001);vary=np.ptp(f[train],axis=0)>0
 src,a=np.where(train[:,None]&train[target]);dst=target[src,a]
 codes=np.stack([(z[dst[a==k]]-z[src[a==k]]).mean(0) for k in range(17)]);codes/=np.maximum(codes.std(0),.1)
 rng=np.random.default_rng(833);allowed=[np.flatnonzero(train[target[i]]) for i in range(len(z))];second=np.array([rng.choice(allowed[i]) for i in dst]);end=target[dst,second]
 best=None;logs=[]
 for width in (512,1024):
  for reg in (.01,1.):
   m=Model();m.mean=mean;m.basis=basis;m.scale=scale;m.dw,m.db=decoder;m.bound=np.maximum(np.abs(z[train]).max(0)*1.25,1);m.codes=codes
   x=np.concatenate([z[src],codes[a]],1);m.centers=x[np.random.default_rng(11).permutation(len(x))[:width]]
   m.fit(z[src],a,z[dst],reg)
   for iteration in range(3):
    val=t.evaluate_transition(m,z,f,target,valid,decoder,vary);trace,_=t.rollout(m,z,f,target,valid,decoder,vary,seed=17);row=dict(width=width,reg=reg,iteration=iteration,one=val['exact_state_rate'],trace=trace['all_steps_exact_rate']);logs.append(row);print(row,flush=True)
    quality=(row['trace'],row['one'])
    if best is None or quality>best[0]:best=(quality,row);m.save(args.output/'model.npz')
    if iteration<2:
     pred=m.step(z[src],a);m.fit(np.concatenate([z[src],pred,pred]),np.concatenate([a,a,second]),np.concatenate([z[dst],z[dst],z[end]]),reg)
 m=load_adapter(args.output/'model.npz');held=t.evaluate_transition(m,z,f,target,test,decoder,vary);trace,_=t.rollout(m,z,f,target,test,decoder,vary)
 result=dict(selection=best[1],validation=logs,test=held,trace=trace,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest());(args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('TEST',held['exact_state_rate'],trace['all_steps_exact_rate'])
if __name__=='__main__':main()
