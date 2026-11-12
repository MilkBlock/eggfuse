"""Evaluate frozen model on native-checked additional entrances; never refit."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import run as base
from dataset import canonical,skeleton
p=argparse.ArgumentParser()
for k in ('corpus','runtime','model','output'):p.add_argument('--'+k,type=Path,required=True)
a=p.parse_args();corpus=json.loads(a.corpus.read_text());runtime=json.loads(a.runtime.read_text());model=dict(np.load(a.model))
base.D=int(model['dimension']);base.POOL_OPS=bool(model['pool_ops']);base.OP=model['op'];base.EDGE=model['edge'];base.LITERAL=model['literal'];labels=list(model['labels'])
old_entries={r['entry_key'] for r in corpus['records']};old_shapes={r['skeleton_key'] for r in corpus['records']};seen=set();rows=[];duplicates=0
for c in runtime['cases']:
    if c['fixed_point']['status']!='pass':raise ValueError('not fixed point')
    entry,_=canonical(c['initial']);final,_=canonical(c['final']);native,_=canonical(c['native_final'])
    if final!=native:raise ValueError('native differs')
    key=base.digest(entry);target=base.digest(final)
    if target!=c['metadata']['expected_known_completion']:raise ValueError('closure changed')
    if key in seen:duplicates+=1;continue
    seen.add(key);plan=base.Plan(entry);x=plan.project(plan.gather(entry))
    rows.append((c,key,skeleton(entry),target,x))
# One fixed GPU function, no completion-dependent control.
import mlx.core as mx
if not mx.metal.is_available():raise RuntimeError('GPU required')
mx.set_default_device(mx.gpu)
l,pj,q,n,b=[mx.array(model[k]) for k in ('linear','first','first_bias','nonlinear','bias')];degree=int(model['degree'])
x=mx.array(np.array([r[4] for r in rows]));scores=x@l+(x@pj+q)**degree@n+b;mx.eval(scores);guess=np.array(scores).argmax(1)
details=[]
for (case,key,shape,target,_),g in zip(rows,guess):
    details.append(dict(id=case['id'],new_entry=key not in old_entries,new_skeleton=shape not in old_shapes,correct=labels[g]==target))
def metric(predicate):
    subset=[r for r in details if predicate(r)];return dict(correct=sum(r['correct'] for r in subset),total=len(subset))
result=dict(scope='Frozen model, completion-derived additional entrances; not natural traffic or novel target classes',
    native_exact_cases=len(runtime['cases']),unique_entries=len(rows),duplicates=duplicates,all_unique=metric(lambda r:True),
    previously_unseen_entries=metric(lambda r:r['new_entry']),previously_unseen_skeletons=metric(lambda r:r['new_skeleton']),
    model_refitted=False,generation_uses_completion_graphs=True,details=details,
    hashes={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ('corpus','runtime','model')})
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='details'},indent=2))
