"""Action-conditioned real quadratic ridge with off-manifold algebra training."""
import importlib.util,json,argparse,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('teacher',ROOT/'benchmarks/cell-real-state/study.py')
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
class Model:
 def __init__(self,d=32):
  self.d=d;self.i,self.j=np.triu_indices(d)
 def features(self,z):
  return np.concatenate([z,z[:,self.i]*z[:,self.j]],axis=1)
 def step(self,z,actions):
  x=self.features(z);out=z.copy()
  for a in range(17):
   keep=actions==a
   out[keep]+=t.predict(x[keep],self.bank[a])
  return np.clip(out,-self.bound,self.bound).astype(np.float16).astype(np.float32)
 def fit(self,x,a,y,reg):
  f=self.features(x)
  self.bank=[t.ridge(f[a==event],(y-x)[a==event],reg) for event in range(17)]
 def save(self,p,mean,basis,scale,decoder):
  np.savez(p,w=np.stack([b[0] for b in self.bank]),bias=np.stack([b[1] for b in self.bank]),bound=self.bound,mean=mean,basis=basis,scale=scale,decoder_w=decoder[0],decoder_b=decoder[1])
def load(path):
 p=np.load(path);m=Model(len(p['scale']));m.bound=p['bound'];m.bank=list(zip(p['w'],p['bias']))
 encode=lambda f:(((f-p['mean'])@p['basis'])/p['scale']).astype(np.float16).astype(np.float32)
 decode=lambda z:t.predict(z,(p['decoder_w'],p['decoder_b']))
 return m,encode,decode

class Adapter:
 def __init__(self,path,precision='fp16'):
  if precision not in ('fp16','fp32'):raise ValueError('precision')
  self.data=np.load(path);self.precision=precision
  self.model=Model(len(self.data['scale']));self.model.bound=self.data['bound']
  self.model.bank=list(zip(self.data['w'],self.data['bias']))
 def encode(self,facts):
  p=self.data;z=((facts-p['mean'])@p['basis'])/p['scale']
  return z.astype(np.float16).astype(np.float32) if self.precision=='fp16' else z.astype(np.float32)
 def step(self,z,actions):
  if self.precision=='fp16':return self.model.step(z,actions)
  x=self.model.features(z);result=z.copy()
  for a,(w,b) in enumerate(self.model.bank):
   keep=actions==a;result[keep]+=x[keep]@w+b
  return np.clip(result,-self.model.bound,self.model.bound).astype(np.float32)
 def decode(self,z):
  p=self.data
  if self.precision=='fp16':return t.predict(z,(p['decoder_w'],p['decoder_b']))
  return z@p['decoder_w']+p['decoder_b']

def load_adapter(weights_path,precision='fp16'):
 return Adapter(weights_path,precision)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 states,facts,target,train,valid,test=t.dataset();vary=np.ptp(facts,axis=0)>0
 mean=facts[train].mean(0);_,_,vt=np.linalg.svd(facts[train]-mean,full_matrices=False);basis=vt[:32].T
 scale=np.maximum(((facts[train]-mean)@basis).std(0),.1);z=(((facts-mean)@basis)/scale).astype(np.float16).astype(np.float32)
 decoder=t.ridge(z[train],facts[train],.001)
 src,act=np.where(train[:,None]&train[target]);dst=target[src,act]
 rng=np.random.default_rng(441);allowed=[np.flatnonzero(train[target[s]]) for s in range(len(z))]
 second=np.array([rng.choice(allowed[d]) for d in dst]);end=target[dst,second]
 # Require both orders of a two-event composition to remain in training.
 mid_other=target[src,second];ok=train[mid_other]
 assert np.array_equal(target[mid_other[ok],act[ok]],end[ok])
 logs=[];best=None
 for reg in (1.,10.):
  m=Model();m.bound=np.maximum(np.abs(z[train]).max(0)*1.25,1.)
  m.fit(z[src],act,z[dst],reg)
  for iteration in range(7):
   val=t.evaluate_transition(m,z,facts,target,valid,decoder,vary)
   trace,_=t.rollout(m,z,facts,target,valid,decoder,vary,seed=17)
   quality=(trace['all_steps_exact_rate'],val['exact_state_rate'],-val['latent_rmse'])
   entry=dict(regularization=reg,iteration=iteration,validation_one_step=val['exact_state_rate'],validation_whole_trace=trace['all_steps_exact_rate']);logs.append(entry);print(entry,flush=True)
   if best is None or quality>best[0]:
    best=(quality,entry.copy());m.save(args.output/'model.npz',mean,basis,scale,decoder)
   if iteration==6:break
   # Label only with training targets; predictions here augment training inputs.
   # Idempotency: reapply a after approximate a and require its same fixed point.
   predicted=m.step(z[src],act)
   # Composition: use the model's output, never the true intermediate embedding.
   other=m.step(z[src[ok]],second[ok])
   x=np.concatenate([z[src],predicted,predicted,other])
   a=np.concatenate([act,act,second,act[ok]])
   y=np.concatenate([z[dst],z[dst],z[end],z[end[ok]]])
   m.fit(x,a,y,reg)
 m,encode,decode=load(args.output/'model.npz')
 held=t.evaluate_transition(m,z,facts,target,test,decoder,vary);trace,_=t.rollout(m,z,facts,target,test,decoder,vary)
 result=dict(scope='standalone finite teacher; real quadratic dynamics; no symbolic repair',gpu_execution=False,semantic_takeover_accepted=False,selection=best[1],validation=logs,test=held,autonomous=trace,training_edges=len(src),training_composition_pairs=int(ok.sum()),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 (args.output/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 print('TEST',held['exact_state_rate'],'TRACE',trace['all_steps_exact_rate'])
if __name__=='__main__':main()
