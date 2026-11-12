"""Fit real completion-structure targets; fold fixed catalog readout into weights."""
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
import run as base
from train_augmented import read_checked
from model_projection import fold_plan
from gpu_model import forward


def main():
 import mlx.core as mx
 p=argparse.ArgumentParser()
 for k in ('corpus','train_runtime','validation_runtime','stress_runtime','admission','model','output'):p.add_argument('--'+k.replace('_','-'),type=Path,required=True)
 a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 if not mx.metal.is_available():raise RuntimeError('Metal required')
 mx.set_default_device(mx.gpu);old=json.loads(a.corpus.read_text())['records'];adm=json.loads(a.admission.read_text());m=dict(np.load(a.model));labels=list(m['labels'])
 for k in ('corpus','train_runtime','validation_runtime','stress_runtime'):
  if adm['hashes'][k]!=hashlib.sha256(getattr(a,k).read_bytes()).hexdigest():raise ValueError('admission provenance mismatch')
 original={s:[r for r in old if r['split']==s] for s in ('train','validation','test')};sets={}
 for split,path in [('train',a.train_runtime),('validation',a.validation_runtime)]:
  rows={r['id']:r for r in read_checked(path)};sets[split]=original[split]+[rows[i] for i in adm['accepted_ids'][split]]
 assert {r['skeleton_key'] for r in sets['train']}.isdisjoint({r['skeleton_key'] for r in sets['validation']+original['test']})
 stress=list({r['entry_key']:r for r in read_checked(a.stress_runtime)}.values())
 base.D=int(m['dimension']);base.POOL_OPS=bool(m['pool_ops']);base.OP=m['op'];base.EDGE=m['edge'];base.LITERAL=m['literal'];base.POOL_NORMALIZATION=str(m.get('pool_normalization','sum'))
 plans={}
 def encode(rows):
  out=[]
  for r in rows:
   key=base.digest(base.structure(r['entry']))
   if key not in plans:plans[key]=fold_plan(base.Plan(r['entry']),m)
   plan=plans[key];out.append(plan.project(plan.gather(r['entry'])))
  return np.array(out)
 tr=encode(sets['train']);va=encode(sets['validation']);target=np.array([labels.index(r['completion_key']) for r in sets['train']]);vy=np.array([labels.index(r['completion_key']) for r in sets['validation']])
 # Completion codebook comes only from known training targets, never test graphs.
 catalog={r['completion_key']:r['completion'] for r in original['train']};codes=[]
 for label in labels:
  plan=base.Plan(catalog[label]);codes.append(plan.project(plan.gather(catalog[label])))
 codes=np.array(codes);codes=(codes-codes.mean(0))/np.maximum(codes.std(0),.05);codes/=np.maximum(np.linalg.norm(codes,axis=1,keepdims=True),1e-8)
 mean=tr.mean(0);scale=np.maximum(tr.std(0),.05);z=(tr-mean)/scale;v=(va-mean)/scale;d=tr.shape[1]
 tf=np.concatenate([z,(1+z@z.T/d)**2],axis=1);vf=np.concatenate([v,(1+v@z.T/d)**2],axis=1)
 logs=[];best=None
 for strength in (0.,.1,.5,1.):
  codebook=np.concatenate([np.sqrt(1-strength)*np.eye(len(labels),dtype=np.float32),np.sqrt(strength)*codes],axis=1).astype(np.float32)
  for reg in (.001,.01,.1,1.,10.):
   w,b=base.fit(tf,codebook[target],reg)
   # Nearest-code squared distance: prediction norm is common to all candidates.
   readout=2*w@codebook.T;bias=2*b@codebook.T-np.sum(codebook*codebook,axis=1)
   scores=vf@readout+bias;hits=scores.argmax(1)==vy;n=len(original['validation'])
   quality=float((hits[:n].mean()+hits[n:].mean())/2)
   loss=float(np.mean((vf@w+b-codebook[vy])**2))
   log=dict(structural_strength=strength,regularization=reg,validation_correct=int(hits.sum()),total=len(hits),balanced_accuracy=quality,target_mse=loss);logs.append(log)
   # MSE across different target geometries is not comparable: ties prefer weaker smoothing.
   ranking=(quality,-strength,-reg)
   if best is None or ranking>best[0]:best=(ranking,log,readout,bias,codebook,w,b)
 _,selection,readout,bias,codebook,w,b=best
 first=z.T/(d*scale[:,None]);q=1-mean@first;linear=readout[:d]/scale[:,None];last_bias=bias-mean@linear;nonlinear=readout[d:]
 model=dict(first=first,first_bias=q,linear=linear,nonlinear=nonlinear,bias=last_bias,kind='quadratic',degree=2,
    dimension=base.D,pool_ops=base.POOL_OPS,pool_normalization=base.POOL_NORMALIZATION,op=base.OP,edge=base.EDGE,literal=base.LITERAL,labels=labels)
 for key in ('state_projection','state_bias'):
  if key in m:model[key]=m[key]
 fn=forward(model)
 def evaluate(rows):
  raw=encode(rows);out=fn(mx.array(raw));mx.eval(out);scores=np.array(out);x=(raw-mean)/scale;features=np.concatenate([x,(1+x@z.T/d)**2],axis=1)
  latent=features@w+b;distances=-np.sum((latent[:,None,:]-codebook[None,:,:])**2,axis=2)
  assert np.array_equal(scores.argmax(1),distances.argmax(1))
  ref=features@readout+bias;np.testing.assert_allclose(scores,ref,atol=.005,rtol=.005)
  truth=np.array([labels.index(r['completion_key']) for r in rows]);hit=scores.argmax(1)==truth
  return dict(correct=int(hit.sum()),total=len(hit)),hit
 test,_=evaluate(original['test']);all_stress,hit=evaluate(stress);oldkeys={r['entry_key'] for r in old};oldgroups={r['skeleton_key'] for r in old}
 def cohort(key,known):
  mask=np.array([r[key] not in known for r in stress]);return dict(correct=int(hit[mask].sum()),total=int(mask.sum()))
 x=mx.array(encode(original['test']));mx.eval(fn(x));timing=[]
 for _ in range(15):
  start=time.perf_counter();mx.eval(fn(x));timing.append((time.perf_counter()-start)*1000)
 result=dict(scope='Structured completion code ridge with exact folded catalog readout; still known-template classification',selection=selection,validation=logs,
    original_test=test,stress_all_unique=all_stress,stress_new_entries=cohort('entry_key',oldkeys),stress_new_skeletons=cohort('skeleton_key',oldgroups),
    state_dimension=d,device_model_bytes=sum(np.asarray(model[k]).nbytes for k in ('first','first_bias','linear','nonlinear','bias')),gpu_median_ms=float(np.median(timing)),
    fixed_matmuls=3,backpropagation=False,runtime_takeover=False,
    hashes={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ('corpus','train_runtime','validation_runtime','stress_runtime','admission','model')})
 np.savez(a.output/'model.npz',**model);(a.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='validation'},indent=2))

if __name__=='__main__':main()
