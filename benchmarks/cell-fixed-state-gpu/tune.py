"""Validation-only selection of baked affine states; one final test evaluation."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import run as base


def main():
    import mlx.core as mx
    p=argparse.ArgumentParser();p.add_argument('--corpus',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu)
    corpus=json.loads(a.corpus.read_text());rows=corpus['records']
    masks={s:np.array([r['split']==s for r in rows]) for s in ('train','validation','test')}
    for s,t in [('train','validation'),('train','test'),('validation','test')]:
        assert {r['skeleton_key'] for r in rows if r['split']==s}.isdisjoint({r['skeleton_key'] for r in rows if r['split']==t})
    labels=sorted({r['completion_key'] for r in rows if r['split']=='train'});target=np.array([labels.index(r['completion_key']) for r in rows])
    trainval=[r for r in rows if r['split']!='test'];is_train=np.array([r['split']=='train' for r in trainval]);yt=np.array([labels.index(r['completion_key']) for r in trainval]);onehot=np.eye(len(labels),dtype=np.float32)[yt]
    trials=[];best=None
    # Fixed candidate grid; no seed sweep and no test-driven model selection.
    for pooling in (False,True):
        for dimension in (32,64):
            for edge_scale in (.35,.5,.8):
                base.POOL_OPS=pooling;base.D=dimension;rng=np.random.default_rng(7419)
                base.OP=rng.normal(0,.4,(5,dimension)).astype(np.float32)
                base.EDGE=rng.normal(0,edge_scale/np.sqrt(dimension),(3,dimension,dimension)).astype(np.float32)
                base.LITERAL=rng.normal(0,.3,(3,4,dimension)).astype(np.float32)
                plans={};raw=[]
                for r in trainval:
                    key=base.digest(base.structure(r['entry']))
                    if key not in plans:plans[key]=base.Plan(r['entry'])
                    raw.append(plans[key].project(plans[key].gather(r['entry'])))
                raw=np.array(raw);mean=raw[is_train].mean(0);scale=np.maximum(raw[is_train].std(0),.05);x=(raw-mean)/scale;centers=x[is_train]
                for degree in (2,3):
                    f=np.concatenate([x,(1+x@centers.T/x.shape[1])**degree],axis=1)
                    for reg in (.001,.01,.1,1.,10.):
                        w,b=base.fit(f[is_train],onehot[is_train],reg)
                        pred=(f[~is_train]@w+b).argmax(1);truth=yt[~is_train];hit=pred==truth
                        macro=float(np.mean([hit[truth==c].mean() for c in np.unique(truth)]))
                        config=dict(pool_ops=pooling,dimension=dimension,edge_scale=edge_scale,degree=degree,regularization=reg)
                        trial=dict(**config,validation_correct=int(hit.sum()),validation_macro=macro);trials.append(trial)
                        # Tied classification scores prefer validation MSE, then smaller state/degree.
                        loss=float(np.mean(((f[~is_train]@w+b)-onehot[~is_train])**2))
                        trial['validation_mse']=loss
                        quality=(macro,float(hit.mean()),-loss,-dimension,-degree)
                        if best is None or quality>best[0]:
                            best=(quality,trial,mean,scale,centers,w,b,base.OP.copy(),base.EDGE.copy(),base.LITERAL.copy())
    _,selected,mean,scale,centers,w,b,base.OP,base.EDGE,base.LITERAL=best;base.POOL_OPS=selected['pool_ops'];base.D=selected['dimension'];degree=selected['degree']
    # Test is encoded/evaluated only after the grid winner has been frozen.
    testrows=[r for r in rows if r['split']=='test'];plans={};pairs=[];raw=[]
    for r in testrows:
        k=base.digest(base.structure(r['entry']))
        if k not in plans:plans[k]=base.Plan(r['entry'])
        pairs.append((plans[k],r['entry']));raw.append(plans[k].project(plans[k].gather(r['entry'])))
    raw=np.array(raw)
    for v,r in zip(raw,testrows):np.testing.assert_allclose(v,base.reference(r['entry']),atol=3e-5,rtol=3e-5)
    first=(centers.T/raw.shape[1])/scale[:,None];q=1-mean@first;linear=w[:raw.shape[1]]/scale[:,None];bias=b-mean@linear;nonlinear=w[raw.shape[1]:]
    gl,gp,gq,gn,gb=[mx.array(v) for v in (linear,first,q,nonlinear,bias)];mx.eval(gl,gp,gq,gn,gb)
    def forward(x):return x@gl+(x@gp+gq)**degree@gn+gb
    fn=mx.compile(forward);v=mx.array(raw);mx.eval(v)
    start=time.perf_counter();out=fn(v);mx.eval(out);cold=(time.perf_counter()-start)*1000;scores=np.array(out)
    x=(raw-mean)/scale;cpu=np.concatenate([x,(1+x@centers.T/x.shape[1])**degree],axis=1)@w+b
    np.testing.assert_allclose(scores,cpu,atol=.003,rtol=.003);assert np.array_equal(scores.argmax(1),cpu.argmax(1))
    truth=target[masks['test']];guess=scores.argmax(1)
    timings=[]
    for factor in (1,16,128):
        batch=mx.tile(v,(factor,1));mx.eval(batch);mx.eval(fn(batch));samples=[]
        for _ in range(10):
            start=time.perf_counter();mx.eval(fn(batch));samples.append((time.perf_counter()-start)*1000)
        timings.append(dict(rows=len(raw)*factor,repeated=factor,median_gpu_ms=float(np.median(samples))))
    samples=[]
    for _ in range(10):
        start=time.perf_counter();encoded=np.array([p.project(p.gather(e)) for p,e in pairs]);pred=fn(mx.array(encoded));mx.eval(pred);np.array(pred);samples.append((time.perf_counter()-start)*1000)
    catalog={r['completion_key']:r['completion'] for r in rows if r['split']=='train'}
    wrong=sum(bool(c!=t and base.extension(r['entry'],catalog[labels[c]]) is not None) for r,c,t in zip(testrows,guess,truth))
    result=dict(scope='Validation-selected fixed whole-Cell GPU state; previously examined development test set',selection=selected,validation=trials,
        test=dict(correct=int((guess==truth).sum()),total=len(truth),wrong_passing_containment=wrong),
        baseline_test=dict(correct=92,total=102),cpu_gpu_top1_equal=True,max_score_abs_error=float(abs(scores-cpu).max()),
        costs=dict(first_gpu_ms=cold,prototype_request_median_ms=float(np.median(samples))),batches=timings,
        state_dimension=raw.shape[1],device_weight_bytes=sum(v.nbytes for v in (linear,first,q,nonlinear,bias)),
        backpropagation=False,gpu_data_dependent_control=False,runtime_takeover=False,
        corpus_sha256=hashlib.sha256(a.corpus.read_bytes()).hexdigest())
    np.savez(a.output/'model.npz',first=first,first_bias=q,linear=linear,nonlinear=nonlinear,bias=bias,degree=degree,
        op=base.OP,edge=base.EDGE,literal=base.LITERAL,dimension=base.D,pool_ops=base.POOL_OPS,labels=labels)
    (a.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='validation'},indent=2))


if __name__=='__main__':main()
