"""Joint dense real encoder/transition/decoder. Finite teacher, no symbolic correction."""
import argparse,hashlib,json,sys,time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cell-real-state'))
import study as teacher

def sigmoid(x): return 1/(1+np.exp(-np.clip(x,-30,30)))
class Model:
 def __init__(self,p,codes,cols,constant): self.p=p;self.codes=codes;self.cols=cols;self.constant=constant
 def encode(self,facts): return np.tanh(facts[:,self.cols]@self.p[0]+self.p[1])
 def step(self,z,a):
  x=np.concatenate([z,self.codes[a]],1); t=np.tanh(x@self.p[2]+self.p[3])
  return np.tanh(z+t@self.p[4]+self.p[5])
 def decode(self,z):
  ans=np.broadcast_to(self.constant,(len(z),len(self.constant))).copy()
  ans[:,self.cols]=sigmoid(z@self.p[6]+self.p[7]); return ans
 def save(self,path): np.savez(path,**{f'p{i}':p for i,p in enumerate(self.p)},codes=self.codes,cols=self.cols,constant=self.constant)
 @classmethod
 def load(cls,path,half=False):
  d=np.load(path);p=[d[f'p{i}'] for i in range(8)]
  if half:p=[x.astype(np.float16).astype(np.float32) for x in p]
  return cls(p,d['codes'],d['cols'],d['constant'])

def evaluate(model,facts,targets,mask,seed=91):
 ids=np.repeat(np.flatnonzero(mask),17);a=np.tile(np.arange(17),mask.sum());dest=targets[ids,a]
 exact=((model.decode(model.step(model.encode(facts[ids]),a))>=.5)==facts[dest]).all(1)
 changed=ids!=dest
 starts=np.tile(np.flatnonzero(mask),4);cur=model.encode(facts[starts]);ids=starts.copy();rng=np.random.default_rng(seed)
 events=rng.integers(0,17,(12,len(ids)));events[2]=15;events[5]=16;events[8]=events[7]
 ok=np.ones(len(ids),bool);steps=[]
 for a in events:
  cur=model.step(cur,a);ids=targets[ids,a]
  hit=((model.decode(cur)>=.5)==facts[ids]).all(1);ok&=hit;steps.append(float(hit.mean()))
 return dict(one_step=float(exact.mean()),changed=float(exact[changed].mean()),no_op=float(exact[~changed].mean()),all_steps=float(ok.mean()),step_rates=steps,trajectories=len(ids),reconstruction=float(((model.decode(model.encode(facts[mask]))>=.5)==facts[mask]).all(1).mean()))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);ap.add_argument('--iterations',type=int,default=3000);args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 start=time.perf_counter();states,facts,targets,train,valid,test=teacher.dataset();rng=np.random.default_rng(407)
 cols=np.flatnonzero(np.ptp(facts[train],axis=0)>0);f=facts[:,cols];n=f.shape[1];d=32;h=128
 codes=rng.normal(size=(17,16)).astype(np.float32);codes/=np.linalg.norm(codes,axis=1,keepdims=True)
 p=[rng.normal(0,.15,(n,d)),np.zeros(d),rng.normal(0,.12,(d+16,h)),np.zeros(h),rng.normal(0,.01,(h,d)),np.zeros(d),rng.normal(0,.1,(d,n)),np.zeros(n)];p=[x.astype(np.float32) for x in p]
 model=Model(p,codes,cols,facts[train][0].copy());m=[np.zeros_like(x) for x in p];v=[np.zeros_like(x) for x in p]
 allowed=[np.flatnonzero(train[targets[i]]) for i in range(len(states))]
 starts=rng.choice(np.flatnonzero(train),8192);ids=starts.copy();events=[];truth=[]
 for _ in range(3):
  a=np.array([rng.choice(allowed[i]) for i in ids]);ids=targets[ids,a];events.append(a);truth.append(ids)
 log=[];best=None
 for iteration in range(1,args.iterations+1):
  ix=rng.integers(0,len(starts),128);z=np.tanh(f[starts[ix]]@p[0]+p[1]);initial=z;zs=[z];tape=[]
  for k in range(3):
   x=np.concatenate([z,codes[events[k][ix]]],1);t=np.tanh(x@p[2]+p[3]);z=np.tanh(z+t@p[4]+p[5]);tape.append((x,t,z));zs.append(z)
  grad=[np.zeros_like(x) for x in p];locals=[]
  for zz,targ in zip(zs,[starts[ix]]+[t[ix] for t in truth]):
   logits=zz@p[6]+p[7];g=(sigmoid(logits)-f[targ])/(len(ix)*n*4)
   grad[6]+=zz.T@g;grad[7]+=g.sum(0);locals.append(g@p[6].T)
  carry=np.zeros_like(z)
  for k in reversed(range(3)):
   x,t,zz=tape[k];g=(carry+locals[k+1])*(1-zz*zz)
   grad[4]+=t.T@g;grad[5]+=g.sum(0);gt=(g@p[4].T)*(1-t*t)
   grad[2]+=x.T@gt;grad[3]+=gt.sum(0);carry=g+(gt@p[2].T)[:,:d]
  ge=(carry+locals[0])*(1-initial*initial);grad[0]+=f[starts[ix]].T@ge;grad[1]+=ge.sum(0)
  for param,g,mm,vv in zip(p,grad,m,v):
   mm*=.9;mm+=.1*g;vv*=.999;vv+=.001*g*g;param-=.003*(mm/(1-.9**iteration))/(np.sqrt(vv/(1-.999**iteration))+1e-8)
  if iteration%500==0:
   val=evaluate(model,facts,targets,valid,17);quality=(val['all_steps'],val['one_step'],val['reconstruction'])
   log.append(dict(iteration=iteration,validation=val));print(iteration,val,flush=True)
   if best is None or quality>best[0]:best=(quality,[x.copy() for x in p],iteration)
 model.p=best[1];model.save(args.output/'model.npz')
 source,act=np.where(train[:,None]&train[targets]);trainhit=((model.decode(model.step(model.encode(facts[source]),act))>=.5)==facts[targets[source,act]]).all(1)
 result=dict(scope='standalone finite teacher; no native/GPU speed claim',selected_iteration=best[2],validation_checkpoints=log,test=evaluate(model,facts,targets,test),test_seed_193=evaluate(model,facts,targets,test,193),half_weights_test=evaluate(Model.load(args.output/'model.npz',True),facts,targets,test),training_edge_accuracy=float(trainhit.mean()),training_reconstruction=float(((model.decode(model.encode(facts[train]))>=.5)==facts[train]).all(1).mean()),parameters=sum(x.size for x in model.p),dimension=d,hidden=h,training_sequences=len(starts),training_sequence_steps=3,teacher_source_sha256=hashlib.sha256(Path(teacher.__file__).read_bytes()).hexdigest(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),seconds=time.perf_counter()-start)
 (args.output/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print('RESULT',result['test'],result['training_edge_accuracy'])
if __name__=='__main__':main()

# External evaluator hook; evaluation results must not select checkpoints.
def load_adapter(weights_path):
    return Model.load(weights_path)
