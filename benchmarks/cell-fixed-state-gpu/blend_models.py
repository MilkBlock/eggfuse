"""Fold two quadratic whole-Cell predictors into one static matrix expression."""
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
import run as base
from train_augmented import read_checked
from gpu_model import forward


def lift(m):
 if str(m.get('kind','quadratic'))!='quadratic' or int(m['degree'])!=2:raise ValueError('quadratic model required')
 first,q,linear,nonlinear,bias=[m[k] for k in ('first','first_bias','linear','nonlinear','bias')]
 if 'state_projection' in m:
  s,t=m['state_projection'],m['state_bias'];q=t@first+q;first=s@first;bias=t@linear+bias;linear=s@linear
 return first,q,linear,nonlinear,bias


def combine(left,right,alpha):
 if alpha==0:return dict(left)
 if alpha==1:return dict(right)
 for k in ('op','edge','literal','labels'):
  if not np.array_equal(left[k],right[k]):raise ValueError('incompatible shared input encoding')
 if str(left.get('pool_normalization','sum'))!=str(right.get('pool_normalization','sum')):raise ValueError('incompatible normalization')
 p,q,l,n,b=lift(left);pp,qq,ll,nn,bb=lift(right)
 result={k:left[k] for k in ('op','edge','literal','labels','dimension','pool_ops')}
 result.update(kind='quadratic',degree=2,pool_normalization=str(left.get('pool_normalization','sum')),
   first=np.concatenate([p,pp],axis=1),first_bias=np.concatenate([q,qq]),linear=(1-alpha)*l+alpha*ll,
   nonlinear=np.concatenate([(1-alpha)*n,alpha*nn],axis=0),bias=(1-alpha)*b+alpha*bb)
 return result


def main():
 import mlx.core as mx
 p=argparse.ArgumentParser()
 for k in ('corpus','validation_runtime','stress_runtime','admission','left','right','output'):p.add_argument('--'+k.replace('_','-'),type=Path,required=True)
 a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 if not mx.metal.is_available():raise RuntimeError('GPU required')
 mx.set_default_device(mx.gpu);old=json.loads(a.corpus.read_text())['records'];adm=json.loads(a.admission.read_text());left=dict(np.load(a.left));right=dict(np.load(a.right))
 for k in ('corpus','validation_runtime','stress_runtime'):
  if hashlib.sha256(getattr(a,k).read_bytes()).hexdigest()!=adm['hashes'][k]:raise ValueError('admission mismatch')
 original={s:[r for r in old if r['split']==s] for s in ('validation','test')};added={r['id']:r for r in read_checked(a.validation_runtime)}
 validation=original['validation']+[added[i] for i in adm['accepted_ids']['validation']];stress=list({r['entry_key']:r for r in read_checked(a.stress_runtime)}.values())
 base.D=int(left['dimension']);base.POOL_OPS=bool(left['pool_ops']);base.OP=left['op'];base.EDGE=left['edge'];base.LITERAL=left['literal'];base.POOL_NORMALIZATION=str(left.get('pool_normalization','sum'));labels=list(left['labels']);plans={}
 def encode(rows):
  out=[]
  for r in rows:
   key=base.digest(base.structure(r['entry']))
   if key not in plans:plans[key]=base.Plan(r['entry'])
   plan=plans[key];out.append(plan.project(plan.gather(r['entry'])))
  return np.array(out)
 def cpu(m,x):
  p,q,l,n,b=lift(m);return x@l+(x@p+q)**2@n+b
 raw=encode(validation);ls,rs=cpu(left,raw),cpu(right,raw);truth=np.array([labels.index(r['completion_key']) for r in validation]);n=len(original['validation']);logs=[];best=None
 for alpha in (0.,.25,.5,.75,1.):
  scores=(1-alpha)*ls+alpha*rs;hit=scores.argmax(1)==truth;quality=float((hit[:n].mean()+hit[n:].mean())/2)
  size=sum(np.asarray(v).nbytes for k,v in combine(left,right,alpha).items() if k in ('first','first_bias','linear','nonlinear','bias'))
  log=dict(alpha=alpha,validation_correct=int(hit.sum()),total=len(hit),balanced_accuracy=quality,device_bytes=size);logs.append(log)
  if best is None or (quality,-size)>best[0]:best=((quality,-size),log)
 _,selection=best;alpha=selection['alpha'];model=combine(left,right,alpha);fn=forward(model)
 def evaluate(rows):
  raw=encode(rows);expected=(1-alpha)*cpu(left,raw)+alpha*cpu(right,raw)
  x=raw if 'state_projection' not in model else raw@model['state_projection']+model['state_bias'];out=fn(mx.array(x));mx.eval(out);scores=np.array(out)
  np.testing.assert_allclose(scores,expected,atol=.005,rtol=.005);assert np.array_equal(scores.argmax(1),expected.argmax(1))
  truth=np.array([labels.index(r['completion_key']) for r in rows]);hit=scores.argmax(1)==truth
  return dict(correct=int(hit.sum()),total=len(hit)),hit,x
 test,_,x=evaluate(original['test']);all_stress,hit,_=evaluate(stress);oldkeys={r['entry_key'] for r in old};oldgroups={r['skeleton_key'] for r in old}
 def cohort(key,known):
  mask=np.array([r[key] not in known for r in stress]);return dict(correct=int(hit[mask].sum()),total=int(mask.sum()))
 device=mx.array(x);mx.eval(fn(device));times=[]
 for _ in range(15):
  start=time.perf_counter();mx.eval(fn(device));times.append((time.perf_counter()-start)*1000)
 result=dict(scope='Validation-selected algebraic blend of frozen quadratic models; known completion catalog only',selection=selection,validation=logs,
  original_test=test,stress_all_unique=all_stress,stress_new_entries=cohort('entry_key',oldkeys),stress_new_skeletons=cohort('skeleton_key',oldgroups),
  fixed_matmuls=3,gpu_median_ms=float(np.median(times)),state_dimension=x.shape[1],backpropagation=False,runtime_takeover=False,
  hashes={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ('corpus','validation_runtime','stress_runtime','admission','left','right')})
 np.savez(a.output/'model.npz',**model);(a.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
