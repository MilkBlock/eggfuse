"""Compile layout into affine scalar projections; fixed whole-Cell GPU inference."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cell-multi-entry-ridge'))
from train import fit, OPS
from dataset import digest, extension

D=32
POOL_OPS=False
RNG=np.random.default_rng(7419)
OP=RNG.normal(0,.4,(5,D)).astype(np.float32)
EDGE=RNG.normal(0,.5/np.sqrt(D),(3,D,D)).astype(np.float32)
LITERAL=RNG.normal(0,.3,(3,4,D)).astype(np.float32)


def structure(entry):
    return [[[op,[[k,s,v if k=='eq' else None] for k,s,v in args]] for op,args in facts] for facts in entry]


class Plan:
    def __init__(self,entry):
        self.reads=[(n,f,p) for n,facts in enumerate(entry) for f,(_,args) in enumerate(facts)
                    for p,(k,s,v) in enumerate(args) if k!='eq']
        positions={v:i for i,v in enumerate(self.reads)};used=set();const=[];coef=[]
        counts=np.zeros(5,np.float32)
        for n,facts in enumerate(entry):
            c=np.zeros(D,np.float32);w=np.zeros((len(self.reads)*4,D),np.float32)
            for f,(op,args) in enumerate(facts):
                c+=OP[OPS.index(op)];counts[OPS.index(op)]+=1
                for p,(kind,sort,v) in enumerate(args):
                    if kind=='eq':
                        if not 0<=v<n:raise ValueError('expected acyclic constructor input')
                        c+=const[v]@EDGE[p];w+=coef[v]@EDGE[p];used.add(v)
                    else:
                        if sort!='i64':raise ValueError('unsupported scalar')
                        slot=positions[n,f,p];w[slot*4:slot*4+4]+=LITERAL[p]
            const.append(c);coef.append(w)
        roots=[i for i in range(len(entry)) if i not in used]
        # All structure propagation happens here, once per shared layout.
        groups=[list(range(len(entry))),roots]
        if POOL_OPS:
            groups += [[i for i,facts in enumerate(entry) for op,_ in facts if op==name] for name in OPS]
        self.bias=np.concatenate([sum((const[i] for i in ids),np.zeros(D,np.float32)) for ids in groups])
        self.weight=np.concatenate([sum((coef[i] for i in ids),np.zeros((len(self.reads)*4,D),np.float32)) for ids in groups],axis=1)
        self.metadata=np.concatenate([counts,[len(entry),len(roots),len(self.reads)]]).astype(np.float32)

    def gather(self,entry):
        return np.array([entry[n][f][1][p][2] for n,f,p in self.reads],np.float32)

    def project(self,v):
        basis=np.stack([v/4,(v/4)**2,np.sin(v),np.cos(v)-1],axis=-1).reshape(-1)
        return np.concatenate([self.bias+basis@self.weight,self.metadata]).astype(np.float32)


def reference(entry):
    # Verification only. Never called by prediction or GPU inference.
    hidden=[];used=set();counts=np.zeros(5,np.float32);scalars=0
    for facts in entry:
        h=np.zeros(D,np.float32)
        for op,args in facts:
            h+=OP[OPS.index(op)];counts[OPS.index(op)]+=1
            for p,(kind,sort,v) in enumerate(args):
                if kind=='eq':h+=hidden[v]@EDGE[p];used.add(v)
                else:
                    s=np.float32(v);h+=np.array([s/4,(s/4)**2,np.sin(s),np.cos(s)-1],np.float32)@LITERAL[p];scalars+=1
        hidden.append(h)
    roots=[i for i in range(len(hidden)) if i not in used]
    groups=[list(range(len(hidden))),roots]
    if POOL_OPS:groups += [[i for i,facts in enumerate(entry) for op,_ in facts if op==name] for name in OPS]
    return np.concatenate([sum((hidden[i] for i in ids),np.zeros(D,np.float32)) for ids in groups]+[counts,[len(hidden),len(roots),scalars]])


def main():
    import mlx.core as mx
    p=argparse.ArgumentParser();p.add_argument('--corpus',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if not mx.metal.is_available():raise RuntimeError('GPU required')
    mx.set_default_device(mx.gpu)
    corpus=json.loads(a.corpus.read_text());rows=corpus['records'];plans={};keys=[]
    start=time.perf_counter()
    for r in rows:
        k=digest(structure(r['entry']));keys.append(k)
        if k not in plans:plans[k]=Plan(r['entry'])
    compile_ms=(time.perf_counter()-start)*1000
    start=time.perf_counter();raw=np.array([plans[k].project(plans[k].gather(r['entry'])) for k,r in zip(keys,rows)])
    encode_ms=(time.perf_counter()-start)*1000
    for row,r in zip(raw,rows):np.testing.assert_allclose(row,reference(r['entry']),atol=3e-5,rtol=3e-5)
    masks={s:np.array([r['split']==s for r in rows]) for s in ('train','validation','test')}
    for s,t in [('train','validation'),('train','test'),('validation','test')]:
        assert {r['skeleton_key'] for r in rows if r['split']==s}.isdisjoint({r['skeleton_key'] for r in rows if r['split']==t})
    labels=sorted({r['completion_key'] for r in rows if r['split']=='train'})
    target=np.array([labels.index(r['completion_key']) for r in rows]);y=np.eye(len(labels),dtype=np.float32)[target]
    mean=raw[masks['train']].mean(0);scale=np.maximum(raw[masks['train']].std(0),.05);x=(raw-mean)/scale
    centers=x[masks['train']];rng=np.random.default_rng(3381)
    projection=rng.normal(0,1/np.sqrt(x.shape[1]),(x.shape[1],512)).astype(np.float32)
    offset=rng.uniform(-1,1,512).astype(np.float32)
    def feature(z,kind):
        if kind=='quadratic':return np.concatenate([z,(1+z@centers.T/z.shape[1])**2],axis=1)
        return np.concatenate([z,np.tanh(z@projection+offset)],axis=1)
    best=None;trials=[]
    for kind in ('quadratic','tanh'):
        f=feature(x,kind)
        for reg in (.001,.1,10.):
            w,b=fit(f[masks['train']],y[masks['train']],reg)
            guess=(f[masks['validation']]@w+b).argmax(1);truth=target[masks['validation']];hit=guess==truth
            macro=float(np.mean([hit[truth==c].mean() for c in np.unique(truth)]))
            trial=dict(kind=kind,regularization=reg,validation_correct=int(hit.sum()),validation_macro=macro);trials.append(trial)
            quality=(macro,float(hit.mean()))
            if best is None or quality>best[0]:best=(quality,trial,w,b)
    _,selection,w,b=best;kind=selection['kind'];test=masks['test'];testrows=[r for r in rows if r['split']=='test']
    # Compile normalization into first projection; GPU receives only whole-Cell vectors.
    gw,gb=mx.array(w),mx.array(b)
    if kind=='quadratic':
        first=(centers.T/x.shape[1])/scale[:,None];first_bias=1-mean@first
    else:first=projection/scale[:,None];first_bias=offset-mean@first
    fp,fb=mx.array(first),mx.array(first_bias)
    # Fold the linear skip's normalization into its readout.
    linear=w[:raw.shape[1]]/scale[:,None];last_bias=b-mean@linear
    gl,gn,gb=mx.array(linear),mx.array(w[raw.shape[1]:]),mx.array(last_bias)
    # Branch is selected ONCE on CPU, never by device data.
    if kind=='quadratic':
        def forward(v):return v@gl+(v@fp+fb)**2@gn+gb
    else:
        def forward(v):return v@gl+mx.tanh(v@fp+fb)@gn+gb
    compiled=mx.compile(forward);mx.eval(gl,gn,gb,fp,fb)
    start=time.perf_counter();v=mx.array(raw[test]);mx.eval(v);upload=(time.perf_counter()-start)*1000
    start=time.perf_counter();out=compiled(v);mx.eval(out);cold=(time.perf_counter()-start)*1000
    start=time.perf_counter();scores=np.array(out);download=(time.perf_counter()-start)*1000
    cpu=feature(x[test],kind)@w+b
    np.testing.assert_allclose(scores,cpu,atol=2e-3,rtol=2e-3);assert np.array_equal(scores.argmax(1),cpu.argmax(1))
    timings=[]
    for factor in (1,16,128):
        vv=mx.tile(v,(factor,1));mx.eval(vv);mx.eval(compiled(vv));samples=[]
        for _ in range(10):
            start=time.perf_counter();mx.eval(compiled(vv));samples.append((time.perf_counter()-start)*1000)
        timings.append(dict(rows=len(testrows)*factor,repetition=factor,median_ms=float(np.median(samples))))
    start=time.perf_counter()
    for _ in range(10):encoded=np.array([plans[k].project(plans[k].gather(r['entry'])) for k,r in zip(keys,rows) if r['split']=='test'])
    gather_project=(time.perf_counter()-start)*1000/10
    start=time.perf_counter()
    for _ in range(10):cs=feature((encoded-mean)/scale,kind)@w+b
    cpu_ms=(time.perf_counter()-start)*1000/10
    # Whole prototype request includes slot extraction, projection, GPU materialization and score return.
    e2e=[]
    for _ in range(10):
        start=time.perf_counter();e=np.array([plans[k].project(plans[k].gather(r['entry'])) for k,r in zip(keys,rows) if r['split']=='test'])
        q=compiled(mx.array(e));mx.eval(q);np.array(q);e2e.append((time.perf_counter()-start)*1000)
    catalog={r['completion_key']:r['completion'] for r in rows if r['split']=='train'};guess=scores.argmax(1);truth=target[test]
    start=time.perf_counter();checks=[extension(r['entry'],catalog[labels[c]]) is not None for r,c in zip(testrows,guess)];check_ms=(time.perf_counter()-start)*1000
    result=dict(scope='Standalone fixed-path whole-Cell GPU ridge; no runtime takeover',selection=selection,validation=trials,
        test=dict(correct=int((guess==truth).sum()),total=len(truth),wrong_passing_containment=sum(bool(ok and g!=t) for ok,g,t in zip(checks,guess,truth))),
        dimensions=dict(cell_state=raw.shape[1],hidden=gn.shape[0],classes=len(labels),layouts=len(plans)),
        execution=dict(gpu=str(mx.default_device()),backpropagation=False,node_traversal_on_gpu=False,data_dependent_gpu_branches=False,
            matmuls=3,nonlinearities=1,all_layouts_in_one_batch=True,cpu_projection='scalar basis times baked layout matrix plus static bias'),
        correctness=dict(affine_projection_matches_reference=len(rows),cpu_gpu_top1_equal=True,max_score_error=float(abs(scores-cpu).max())),
        costs_ms=dict(compile_all_layouts=compile_ms,encode_all_rows=encode_ms,test_gather_and_projection=gather_project,
            test_upload=upload,first_gpu_call=cold,test_download=download,cpu_numeric=cpu_ms,
            prototype_request_median=float(np.median(e2e)),necessary_containment=check_ms),batches=timings,
        storage=dict(layout_projection_bytes=sum(p.weight.nbytes+p.bias.nbytes+p.metadata.nbytes for p in plans.values()),
            device_weights_bytes=first.nbytes+first_bias.nbytes+linear.nbytes+w[raw.shape[1]:].nbytes+last_bias.nbytes,
            test_input_bytes=raw[test].nbytes),
        limitations=['CPU affine projection remains and is charged','export adapter, not live compressed-slot integration',
            'acyclic static topology per layout; no dynamic Eq input support','catalog classification, not generative completion',
            'no derivability certificate or lifecycle integration','repeated throughput rows are not additional accuracy samples'],
        corpus_sha256=hashlib.sha256(a.corpus.read_bytes()).hexdigest())
    np.savez(a.output/'model.npz',first=first,first_bias=first_bias,linear=linear,nonlinear=w[raw.shape[1]:],bias=last_bias,kind=kind,labels=labels)
    (a.output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
