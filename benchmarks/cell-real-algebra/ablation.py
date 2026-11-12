"""Predeclared 2x2 ablation, no new model selection or hyperparameter search."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from study import Model,t

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 _,facts,target,train,valid,test=t.dataset();vary=np.ptp(facts,axis=0)>0
 mean=facts[train].mean(0);_,_,vt=np.linalg.svd(facts[train]-mean,full_matrices=False);basis=vt[:32].T
 scale=np.maximum(((facts[train]-mean)@basis).std(0),.1);z=(((facts-mean)@basis)/scale).astype(np.float16).astype(np.float32)
 decoder=t.ridge(z[train],facts[train],.001)
 src,act=np.where(train[:,None]&train[target]);dst=target[src,act]
 rng=np.random.default_rng(441);allowed=[np.flatnonzero(train[target[s]]) for s in range(len(z))]
 second=np.array([rng.choice(allowed[d]) for d in dst]);end=target[dst,second]
 other_ids=target[src,second];ok=train[other_ids]
 assert np.array_equal(target[other_ids[ok],act[ok]],end[ok])
 arms=[]
 for augmented in (False,True):
  for clip in (False,True):
   m=Model();m.bound=np.maximum(np.abs(z[train]).max(0)*1.25,1.) if clip else np.full(32,np.inf)
   m.fit(z[src],act,z[dst],10.)
   for _ in range(3 if augmented else 0):
    pred=m.step(z[src],act);other=m.step(z[src[ok]],second[ok])
    x=np.concatenate([z[src],pred,pred,other]);events=np.concatenate([act,act,second,act[ok]])
    y=np.concatenate([z[dst],z[dst],z[end],z[end[ok]]]);m.fit(x,events,y,10.)
   result=t.evaluate_transition(m,z,facts,target,test,decoder,vary)
   trace,_=t.rollout(m,z,facts,target,test,decoder,vary)
   name=('augmented' if augmented else 'baseline')+('-clip' if clip else '-no-clip')
   m.save(a.output/(name+'.npz'),mean,basis,scale,decoder)
   arms.append(dict(name=name,augmentation_iterations=3 if augmented else 0,clipping_during_training_and_inference=clip,test=result,autonomous=trace))
   print(name,result['exact_state_rate'],result['changed']['exact_state_rate'],result['no_op']['exact_state_rate'],trace['all_steps_exact_rate'],flush=True)
 result=dict(scope='fixed reg=10, augmentation iterations=3; no test-based model selection',regularization=10.,arms=arms,semantic_takeover_accepted=False,source_sha256={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ['ablation.py','study.py']})
 (a.output/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
if __name__=='__main__':main()
