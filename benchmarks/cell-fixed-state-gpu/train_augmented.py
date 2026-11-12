"""Ridge on native-checked derived-fact augmentations; original/stress tests frozen."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import run as base
from dataset import canonical,skeleton


def read_checked(path):
    data=json.loads(path.read_text());rows=[]
    for c in data['cases']:
        if c['fixed_point']['status']!='pass':raise ValueError('missing fixed point')
        entry,_=canonical(c['initial']);final,_=canonical(c['final']);native,_=canonical(c['native_final'])
        key=base.digest(final)
        if final!=native or key!=c['metadata']['expected_known_completion']:raise ValueError('completion mismatch')
        rows.append(dict(id=c['id'],entry=entry,entry_key=base.digest(entry),skeleton_key=skeleton(entry),completion_key=key,
            parent=c['metadata']['parent'],parent_split=c['metadata'].get('parent_split','test')))
    return rows


def main():
    import mlx.core as mx
    p=argparse.ArgumentParser()
    for k in ('corpus','train_runtime','validation_runtime','stress_runtime','model','output'):p.add_argument('--'+k.replace('_','-'),type=Path,required=True)
    p.add_argument('--center-budgets',default='all',help='comma-separated training-only center budgets or all')
    p.add_argument('--feature-kinds',default='quadratic')
    p.add_argument('--pool-normalization',choices=['sum','mean','sqrt'],default='sum')
    p.add_argument('--validation-only',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu)
    old=json.loads(a.corpus.read_text())['records'];parents={r['id']:r for r in old};m=dict(np.load(a.model))
    base.POOL_NORMALIZATION=a.pool_normalization
    base.D=int(m['dimension']);base.POOL_OPS=bool(m['pool_ops']);base.OP=m['op'];base.EDGE=m['edge'];base.LITERAL=m['literal']
    original={s:[r for r in old if r['split']==s] for s in ('train','validation','test')}
    groups={s:{r['skeleton_key'] for r in rs} for s,rs in original.items()}
    stress=read_checked(a.stress_runtime);stress=list({r['entry_key']:r for r in stress}.values());stressgroups={r['skeleton_key'] for r in stress}
    accepted={};rejected={};seen={r['entry_key'] for r in old}
    for split,path in [('train',a.train_runtime),('validation',a.validation_runtime)]:
        admitted=[];reasons=collections.Counter();forbidden=set().union(*(g for s,g in groups.items() if s!=split),stressgroups)
        for r in read_checked(path):
            if r['parent'] not in parents or parents[r['parent']]['split']!=split or r['parent_split']!=split:raise ValueError('parent split mismatch')
            if r['skeleton_key'] in forbidden:reasons['protected_split_or_stress_skeleton']+=1;continue
            if r['entry_key'] in seen:reasons['duplicate_entry']+=1;continue
            seen.add(r['entry_key']);admitted.append(r);groups[split].add(r['skeleton_key'])
        accepted[split]=admitted;rejected[split]=dict(reasons)
    assert groups['train'].isdisjoint(groups['validation']) and groups['train'].isdisjoint(groups['test'])
    assert groups['validation'].isdisjoint(groups['test'])
    training=original['train']+accepted['train'];validation=original['validation']+accepted['validation']
    labels=list(m['labels']);plans={}
    def encode(rows):
        values=[]
        for r in rows:
            key=base.digest(base.structure(r['entry']))
            if key not in plans:plans[key]=base.Plan(r['entry'])
            plan=plans[key];values.append(plan.project(plan.gather(r['entry'])))
        return np.array(values)
    tr=encode(training);va=encode(validation);y=np.eye(len(labels),dtype=np.float32)[[labels.index(r['completion_key']) for r in training]]
    truth=np.array([labels.index(r['completion_key']) for r in validation]);mean=tr.mean(0);scale=np.maximum(tr.std(0),.05);normalized=(tr-mean)/scale
    def feature(raw):
        x=(raw-mean)/scale
        if kind=='quadratic':hidden=(1+x@centers.T/x.shape[1])**2
        else:
            distance=np.maximum(np.sum(x*x,axis=1)[:,None]+np.sum(centers*centers,axis=1)-2*x@centers.T,0)
            hidden=np.exp(-distance/(x.shape[1]*radius))
        return np.concatenate([x,hidden],axis=1)
    logs=[];best=None
    for token in a.center_budgets.split(','):
        budget=len(training) if token=='all' else min(int(token),len(training))
        if budget<=0:raise ValueError('positive center budget required')
        if budget==len(training):indices=np.arange(len(training))
        else:
            # Greedy coverage uses training inputs only, never labels or validation.
            chosen=[];distance=np.full(len(training),np.inf)
            next_index=int(np.argmin(np.sum(normalized**2,axis=1)))
            for _ in range(budget):
                chosen.append(next_index)
                distance=np.minimum(distance,np.sum((normalized-normalized[next_index])**2,axis=1))
                distance[chosen]=-np.inf;next_index=int(np.argmax(distance))
            indices=np.array(chosen)
        centers=normalized[indices]
        for kind in a.feature_kinds.split(','):
            if kind not in ('quadratic','radial'):raise ValueError('unknown feature kind')
            for radius in ((1.,) if kind=='quadratic' else (.25,1.,4.)):
                tf,vf=feature(tr),feature(va)
                for reg in (.001,.01,.1,1.,10.):
                    w,b=base.fit(tf,y,reg);pred=vf@w+b;hits=pred.argmax(1)==truth
                    cohorts=[hits[:len(original['validation'])]]
                    if accepted['validation']:cohorts.append(hits[len(original['validation']):])
                    quality=float(np.mean([h.mean() for h in cohorts]));loss=float(np.mean((pred-np.eye(len(labels))[truth])**2))
                    row=dict(kind=kind,radius=radius,centers=budget,regularization=reg,validation_correct=int(hits.sum()),validation_total=len(hits),
                        original_correct=int(hits[:len(original['validation'])].sum()),augmented_correct=int(hits[len(original['validation']):].sum()),balanced_accuracy=quality,mse=loss)
                    logs.append(row)
                    # Preserve validation accuracy first; tied accuracy prefers smaller model, then MSE.
                    ranking=(quality,-budget,-loss)
                    if best is None or ranking>best[0]:best=(ranking,row,w,b,centers.copy(),indices.copy(),kind,radius)
    _,selected,w,b,centers,indices,kind,radius=best;d=tr.shape[1]
    if kind=='quadratic':
        first=(centers.T/d)/scale[:,None];q=1-mean@first;square=np.zeros(d,np.float32)
    else:
        square=1/(scale*scale*d*radius)
        first=2*centers.T/(scale[:,None]*d*radius)+2*(mean*square)[:,None]
        q=-np.sum(centers*centers,axis=1)/(d*radius)-np.sum(mean*mean*square)-2*(mean/scale)@centers.T/(d*radius)
    linear=w[:d]/scale[:,None];bias=b-mean@linear;nonlinear=w[d:]
    if a.validation_only:
        report=dict(selection=selected,validation=logs,pool_normalization=a.pool_normalization,training_rows=len(training),validation_rows=len(validation))
        (a.output/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='validation'},indent=2));return
    gl,gp,gq,gn,gb,gs=[mx.array(v) for v in (linear,first,q,nonlinear,bias,square)];mx.eval(gl,gp,gq,gn,gb,gs)
    if kind=='quadratic':fn=mx.compile(lambda x:x@gl+(x@gp+gq)**2@gn+gb)
    else:fn=mx.compile(lambda x:x@gl+mx.exp(mx.minimum(x@gp+gq-mx.sum(x*x*gs,axis=1,keepdims=True),0))@gn+gb)
    def evaluate(rows):
        raw=encode(rows);v=mx.array(raw);out=fn(v);mx.eval(out);scores=np.array(out);ref=feature(raw)@w+b
        np.testing.assert_allclose(scores,ref,atol=.005,rtol=.005);assert np.array_equal(scores.argmax(1),ref.argmax(1))
        gt=np.array([labels.index(r['completion_key']) for r in rows]);hits=scores.argmax(1)==gt
        return dict(correct=int(hits.sum()),total=len(rows)),hits
    original_result,_=evaluate(original['test']);stress_result,hit=evaluate(stress)
    oldkeys={r['entry_key'] for r in old};oldgroups={r['skeleton_key'] for r in old}
    def cohort(pred):
        mask=np.array([pred(r) for r in stress]);return dict(correct=int(hit[mask].sum()),total=int(mask.sum()))
    timings=[];v=mx.array(encode(original['test']));mx.eval(fn(v))
    for _ in range(15):
        start=time.perf_counter();mx.eval(fn(v));timings.append((time.perf_counter()-start)*1000)
    result=dict(scope='Fixed affine typed layout + augmented ridge, no backprop; source-isolated generated entrances',
        pool_normalization=a.pool_normalization,admitted={k:len(v) for k,v in accepted.items()},rejected=rejected,training_rows=len(training),validation_rows=len(validation),
        selection=selected,validation=logs,original_test=original_result,stress_all_unique=stress_result,
        stress_new_entries=cohort(lambda r:r['entry_key'] not in oldkeys),stress_new_skeletons=cohort(lambda r:r['skeleton_key'] not in oldgroups),
        baseline=dict(original_test=dict(correct=97,total=102),stress_new_entries=dict(correct=20,total=90),stress_new_skeletons=dict(correct=18,total=82)),
        gpu_median_ms=float(np.median(timings)),state_dimension=d,hidden=len(centers),center_selection_training_ids=[training[i]['id'] for i in indices],fixed_matmuls=3,
        model_bytes=sum(v.nbytes for v in (linear,first,q,nonlinear,bias,square)),runtime_takeover=False,
        hashes={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ('corpus','train_runtime','validation_runtime','stress_runtime','model')},
        accepted_ids={k:[r['id'] for r in rs] for k,rs in accepted.items()})
    np.savez(a.output/'model.npz',first=first,first_bias=q,linear=linear,nonlinear=nonlinear,bias=bias,pool_normalization=a.pool_normalization,degree=2,kind=kind,radial_square=square,
        op=base.OP,edge=base.EDGE,literal=base.LITERAL,dimension=base.D,pool_ops=base.POOL_OPS,labels=labels)
    (a.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('accepted_ids','hashes','validation','center_selection_training_ids')},indent=2))


if __name__=='__main__':main()
