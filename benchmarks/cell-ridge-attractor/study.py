"""Continuous radial denoising after frozen ridge transition; no lookup/repair."""
import sys,argparse,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/cell-ridge-enhanced'))
import anchored as base

def features(z,c,width):
 d=np.maximum((z*z).sum(1)[:,None]+(c*c).sum(1)-2*z@c.T,0)
 return np.concatenate([z,np.exp(-d/width)],1)
class Adapter:
 def __init__(self,path):
  p=dict(np.load(path));self.p=p;self.original=base.Adapter(Path(str(p['base_path'])))
 def encode(self,f):return self.original.encode(f)
 def step(self,z,a):
  z=self.original.step(z,a);p=self.p
  for _ in range(int(p['passes'])):
   z=z+float(p['strength'])*(features(z,p['centers'],float(p['width']))@p['w']+p['b'])
   z=np.clip(z,-self.original.model.bound,self.original.model.bound).astype(np.float16).astype(np.float32)
  return z
 def decode(self,z):return self.original.decode(z)
def load_adapter(path):return Adapter(path)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 path=ROOT/'out/cell-ridge-enhanced/anchored/model.npz';original=base.Adapter(path)
 _,facts,target,train,valid,test=base.t.dataset();z=original.encode(facts);decoder=(original.p['decoder_w'],original.p['decoder_b']);vary=np.ptp(facts[train],axis=0)>0
 src,act=np.where(train[:,None]&train[target]);dst=target[src,act]
 predicted=original.step(z[src],act)
 rng=np.random.default_rng(994);centers=z[train];logs=[];best=None
 for noise in (.05,.2):
  clean=np.repeat(z[train],8,axis=0);noisy=clean+rng.normal(0,noise,clean.shape)
  x=np.concatenate([z[train],predicted,noisy]);y=np.concatenate([z[train],z[dst],clean])
  for width in (8.,32.):
   f=features(x,centers,width)
   for reg in (.01,1.):
    scale=np.maximum(f.std(0),.05);w,b=base.weighted_ridge(f/scale,y-x,np.ones(len(x)),reg);w=(w/scale[:,None]).astype(np.float32)
    for strength in (.25,1.):
     for passes in (1,2):
      pars=dict(base_path=str(path),centers=centers,width=width,w=w,b=b,strength=strength,passes=passes)
      np.savez(args.output/'candidate.npz',**pars);m=Adapter(args.output/'candidate.npz')
      val=base.t.evaluate_transition(m,z,facts,target,valid,decoder,vary);trace,_=base.t.rollout(m,z,facts,target,valid,decoder,vary,seed=17)
      row=dict(noise=noise,width=width,reg=reg,strength=strength,passes=passes,one=val['exact_state_rate'],trace=trace['all_steps_exact_rate']);logs.append(row);print(row,flush=True)
      quality=(row['trace'],row['one'])
      if best is None or quality>best[0]:best=(quality,row);np.savez(args.output/'model.npz',**pars)
 m=Adapter(args.output/'model.npz');held=base.t.evaluate_transition(m,z,facts,target,test,decoder,vary);trace,_=base.t.rollout(m,z,facts,target,test,decoder,vary)
 result=dict(selection=best[1],validation=logs,test=held,autonomous=trace,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='standalone finite teacher; no GPU/native claim')
 (args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('RESULT',best[1],held['exact_state_rate'],trace['all_steps_exact_rate'])
if __name__=='__main__':main()
