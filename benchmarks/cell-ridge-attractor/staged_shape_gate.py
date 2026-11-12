"""Smooth residual suppression for near-idempotent continuous transitions."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from staged import Adapter as Prior,base,kernel,ROOT
class Adapter:
 def __init__(self,path):
  self.p=dict(np.load(path));self.prior=Prior(Path(str(self.p['prior_path'])))
 def encode(self,f):return self.prior.encode(f)
 def decode(self,z):return self.prior.decode(z)
 def step(self,z,a):
  proposed=self.prior.step(z,a);delta=proposed-z
  g=-np.expm1(-(np.sum(delta*delta,axis=1,keepdims=True)/float(self.p['scale'])**2)**float(self.p['power']))
  return z+g*delta
def load_adapter(path):return Adapter(path)
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 path=ROOT/'out/cell-ridge-attractor/staged/model.npz';prior=Prior(path)
 _,facts,target,train,valid,test=base.t.dataset();z=prior.encode(facts)
 src,a=np.where(train[:,None]&train[target]);dst=target[src,a];norm=np.linalg.norm(z[dst]-z[src],axis=1);median=float(np.median(norm[norm>1e-7]))
 best=None;rows=[]
 for scale,power in [(median*s,p) for s in (.25,.4,.5) for p in (.5,2.,3.)]:
  pars=dict(prior_path=str(path),scale=scale,power=power);np.savez(args.output/'candidate.npz',**pars);m=Adapter(args.output/'candidate.npz');val=kernel.score(m,z,facts,target,valid);row=dict(scale=scale,power=power,validation=val);rows.append(row);print(row,flush=True)
  q=(val['trace'],val['single'])
  if best is None or q>best[0]:best=(q,row);np.savez(args.output/'model.npz',**pars)
 m=Adapter(args.output/'model.npz');result=dict(selection=best[1],validation=rows,training_change_median=median,test=kernel.score(m,z,facts,target,test),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 (args.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print('RESULT',result['test'])
if __name__=='__main__':main()
