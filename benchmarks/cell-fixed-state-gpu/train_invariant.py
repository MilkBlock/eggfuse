"""Train-only generalized-eigenvalue projection, folded into affine layout plans.
No gradients; validation chooses projection rank/regularization and ridge.
"""
import argparse,json,hashlib,time
from pathlib import Path
import numpy as np
import run as base
from train_augmented import read_checked
from gpu_model import forward


def main():
 import mlx.core as mx
 p=argparse.ArgumentParser()
 for k in ('corpus','train_runtime','validation_runtime','stress_runtime','admission','model','output'):p.add_argument('--'+k.replace('_','-'),type=Path,required=True)
 p.add_argument('--residual-ranks',default='0',help='training PCA directions retained alongside discriminant directions')
 a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 if not mx.metal.is_available():raise RuntimeError('Metal GPU required')
 mx.set_default_device(mx.gpu)
 old=json.loads(a.corpus.read_text())['records'];admission=json.loads(a.admission.read_text());m=dict(np.load(a.model))
 for k in ('corpus','train_runtime','validation_runtime','stress_runtime'):
  if admission['hashes'][k]!=hashlib.sha256(getattr(a,k).read_bytes()).hexdigest():raise ValueError('admission provenance mismatch')
 original={s:[r for r in old if r['split']==s] for s in ('train','validation','test')};sets={}
 for split,path in [('train',a.train_runtime),('validation',a.validation_runtime)]:
  rows={r['id']:r for r in read_checked(path)};sets[split]=original[split]+[rows[i] for i in admission['accepted_ids'][split]]
 assert {r['skeleton_key'] for r in sets['train']}.isdisjoint({r['skeleton_key'] for r in sets['validation']+original['test']})
 stress=list({r['entry_key']:r for r in read_checked(a.stress_runtime)}.values())
 base.D=int(m['dimension']);base.POOL_OPS=bool(m['pool_ops']);base.OP=m['op'];base.EDGE=m['edge'];base.LITERAL=m['literal'];labels=list(m['labels'])
 plans={}
 def encode(rows):
  out=[]
  for r in rows:
   k=base.digest(base.structure(r['entry']))
   if k not in plans:plans[k]=base.Plan(r['entry'])
   plan=plans[k];out.append(plan.project(plan.gather(r['entry'])))
  return np.array(out)
 tr=encode(sets['train']);va=encode(sets['validation']);y=np.array([labels.index(r['completion_key']) for r in sets['train']]);vy=np.array([labels.index(r['completion_key']) for r in sets['validation']]);targets=np.eye(len(labels),dtype=np.float32)[y]
 mean=tr.mean(0).astype(np.float64);scale=np.maximum(tr.std(0),.05).astype(np.float64);z=(tr-mean)/scale;v=(va-mean)/scale
 classmean=np.array([z[y==c].mean(0) for c in range(len(labels))]);residual=z-classmean[y];sw=residual.T@residual/len(z);between=classmean[y].T@classmean[y]/len(z)
 eig,vec=np.linalg.eigh(sw);logs=[];best=None
 pe,pv=np.linalg.eigh(z.T@z/len(z));pca=pv[:,np.argsort(pe)[::-1]]
 pca=pca/np.maximum((z@pca).std(0),.05)
 for shrink in (.01,.1,1.,10.):
  whiten=(vec/np.sqrt(np.maximum(eig,0)+shrink))@vec.T
  spectrum,directions=np.linalg.eigh(whiten@between@whiten)
  basis=whiten@directions[:,np.argsort(spectrum)[::-1]]
  effective_rank=int(np.sum(spectrum>max(float(spectrum.max())*1e-8,1e-10)))
  for discriminant_rank in (8,16,23,32,64):
   if discriminant_rank>effective_rank:continue
   discriminant=basis[:,:discriminant_rank];discriminant=discriminant/np.maximum((z@discriminant).std(0),.05)
   for residual_rank in [int(t) for t in a.residual_ranks.split(',')]:
    if residual_rank<0 or residual_rank>z.shape[1]:raise ValueError('invalid residual rank')
    q=np.concatenate([discriminant,pca[:,:residual_rank]],axis=1);rank=q.shape[1]
    tx=(z@q).astype(np.float32);vx=(v@q).astype(np.float32)
    tf=np.concatenate([tx,(1+tx@tx.T/rank)**2],axis=1);vf=np.concatenate([vx,(1+vx@tx.T/rank)**2],axis=1)
    for reg in (.001,.01,.1,1.,10.):
     w,b=base.fit(tf,targets,reg);scores=vf@w+b;hit=scores.argmax(1)==vy;n=len(original['validation'])
     quality=float((hit[:n].mean()+hit[n:].mean())/2);loss=float(np.mean((scores-np.eye(len(labels))[vy])**2))
     log=dict(shrink=shrink,rank=rank,discriminant_rank=discriminant_rank,residual_rank=residual_rank,regularization=reg,validation_correct=int(hit.sum()),total=len(hit),balanced_accuracy=quality,mse=loss);logs.append(log)
     ranking=(quality,-rank,-loss)
     if best is None or ranking>best[0]:best=(ranking,log,q.copy(),tx.copy(),w,b)
 _,selection,q,centers,w,b=best;rank=q.shape[1]
 # raw-state affine projection is folded into every template, not executed on GPU.
 state_projection=(q/scale[:,None]).astype(np.float32);state_bias=(-mean@state_projection).astype(np.float32)
 model=dict(first=(centers.T/rank).astype(np.float32),first_bias=np.ones(len(centers),np.float32),linear=w[:rank],nonlinear=w[rank:],bias=b,
     state_projection=state_projection,state_bias=state_bias,degree=2,kind='quadratic',op=base.OP,edge=base.EDGE,literal=base.LITERAL,dimension=base.D,pool_ops=base.POOL_OPS,labels=labels)
 fn=forward(model)
 def evaluate(rows):
  raw=encode(rows);x=raw@state_projection+state_bias;out=fn(mx.array(x));mx.eval(out);scores=np.array(out)
  ref=np.concatenate([x,(1+x@centers.T/rank)**2],axis=1)@w+b
  np.testing.assert_allclose(scores,ref,atol=.003,rtol=.003);assert np.array_equal(scores.argmax(1),ref.argmax(1))
  truth=np.array([labels.index(r['completion_key']) for r in rows]);hit=scores.argmax(1)==truth
  return dict(correct=int(hit.sum()),total=len(hit)),hit
 test,_=evaluate(original['test']);stress_all,hit=evaluate(stress);oldkeys={r['entry_key'] for r in old};oldgroups={r['skeleton_key'] for r in old}
 def cohort(key,known):
  mask=np.array([r[key] not in known for r in stress]);return dict(correct=int(hit[mask].sum()),total=int(mask.sum()))
 # Verify eliminating the 456-dimensional intermediate is algebraically correct.
 max_error=0.;folded_bytes=0
 for r in old:
  k=base.digest(base.structure(r['entry']))
  if k not in plans:plans[k]=base.Plan(r['entry'])
  plan=plans[k];offset=np.concatenate([plan.bias,plan.metadata])@state_projection+state_bias
  weight=plan.weight@state_projection[:len(plan.bias)];values=plan.gather(r['entry']);basis_values=np.stack([values/4,(values/4)**2,np.sin(values),np.cos(values)-1],axis=-1).reshape(-1)
  expected=plan.project(values)@state_projection+state_bias;actual=offset+basis_values@weight
  np.testing.assert_allclose(actual,expected,atol=1e-4,rtol=1e-4);max_error=max(max_error,float(abs(actual-expected).max()))
 for plan in plans.values():folded_bytes+=plan.weight.shape[0]*rank*4+rank*4
 x=mx.array(encode(original['test'])@state_projection+state_bias);mx.eval(fn(x));timing=[]
 for _ in range(15):
  start=time.perf_counter();mx.eval(fn(x));timing.append((time.perf_counter()-start)*1000)
 result=dict(scope='Train-only same-completion scatter projection; fixed GPU ridge, no backprop',selection=selection,validation=logs,
     original_test=test,stress_all_unique=stress_all,stress_new_entries=cohort('entry_key',oldkeys),stress_new_skeletons=cohort('skeleton_key',oldgroups),
     state_dimension=rank,old_dimension=tr.shape[1],gpu_median_ms=float(np.median(timing)),folding_max_error=max_error,
     compiled_layout_count=len(plans),compiled_projection_bytes=folded_bytes,device_model_bytes=sum(np.asarray(model[k]).nbytes for k in ('first','first_bias','linear','nonlinear','bias')),
     runtime_takeover=False,hashes={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ('corpus','train_runtime','validation_runtime','stress_runtime','admission','model')})
 np.savez(a.output/'model.npz',**model);(a.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='validation'},indent=2))

if __name__=='__main__':main()
