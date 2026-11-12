"""Shared entry-layout GPU encoder + frozen fitted ridge; no backpropagation.
Standalone adapter over native-checked exports, not a runtime takeover.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'cell-multi-entry-ridge'))
from train import Encoder, OPS, features
from dataset import digest, extension


def layout(entry):
    # Integer references are static wiring, never numerical model inputs.
    return [[[op, [[k,s,v if k=='eq' else None] for k,s,v in args]]
             for op,args in facts] for facts in entry]


class Plan:
    def __init__(self, entry):
        self.structure=layout(entry)
        self.reads=[]; self.nodes=[]; used=set(); self.counts=np.zeros(5,np.float32)
        for ni,facts in enumerate(entry):
            compiled=[]
            for fi,(op,args) in enumerate(facts):
                self.counts[OPS.index(op)]+=1; edges=[]; scalars=[]
                for pos,(kind,sort,value) in enumerate(args):
                    if kind=='eq':
                        if not 0<=value<ni: raise ValueError('non-topological input')
                        edges.append((pos,value));used.add(value)
                    else:
                        if sort!='i64': raise ValueError('unsupported scalar')
                        scalars.append((pos,len(self.reads)));self.reads.append((ni,fi,pos))
                compiled.append((OPS.index(op),edges,scalars))
            self.nodes.append(compiled)
        self.roots=[i for i in range(len(entry)) if i not in used]

    def gather(self, entry):
        return [entry[n][f][1][p][2] for n,f,p in self.reads]

    def encode(self, x, enc):
        import mlx.core as mx
        hidden=[];batch=x.shape[0]
        for facts in self.nodes:
            value=mx.zeros((batch,32))
            for op,edges,scalars in facts:
                v=mx.broadcast_to(enc['operator'][op],(batch,32))
                for pos,node in edges:v=v+hidden[node]@enc['position'][pos]
                for pos,slot in scalars:
                    s=x[:,slot]; z=mx.stack([s/4,mx.sin(s),mx.cos(s)],axis=1)
                    v=v+z@enc['literal'][pos]
                value=value+mx.tanh(v)
            hidden.append(value)
        h=mx.stack(hidden,axis=1)
        return mx.concatenate([mx.sum(h,axis=1),mx.max(h,axis=1),
            mx.sum(mx.stack([hidden[i] for i in self.roots],axis=1),axis=1),
            mx.broadcast_to(mx.array(self.counts),(batch,5)),
            mx.full((batch,1),len(hidden)),mx.full((batch,1),len(self.roots)),
            mx.sum(x,axis=1,keepdims=True),mx.sum(x*x,axis=1,keepdims=True)],axis=1)


def main():
    import mlx.core as mx
    p=argparse.ArgumentParser()
    for name in ('corpus','model','catalog','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--repeat',type=int,default=3)
    p.add_argument('--eager',action='store_true')
    a=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal GPU required; no CPU fallback')
    mx.set_default_device(mx.gpu)
    corpus=json.loads(a.corpus.read_text());m=dict(np.load(a.model));catalog=json.loads(a.catalog.read_text())
    if str(m['catalog_sha256'])!=digest(catalog):raise ValueError('catalog mismatch')
    if str(m['kind'])!='quadratic' or bool(m['field_moments']):raise ValueError('quadratic encoder model required')
    rows=[r for r in corpus['records'] if r['split']=='test']
    # No completion labels enter layout compilation or grouping.
    start=time.perf_counter(); plans={}; groups=collections.defaultdict(list)
    for i,r in enumerate(rows):
        key=digest(layout(r['entry']))
        if key not in plans:plans[key]=Plan(r['entry'])
        groups[key].append(i)
    compile_ms=(time.perf_counter()-start)*1000
    encoders=[Encoder(int(seed)) for seed in m['encoder_seeds']]
    ge=[{k:mx.array(getattr(e,k)) for k in ('operator','position','literal')} for e in encoders]
    gm={k:mx.array(m[k]) for k in ('mean','scale','centers','w','b','codes')}
    # Orthogonal code readout is folded into trained dense weights, not a lookup.
    readout=gm['w']@gm['codes'].T; bias=gm['b']@gm['codes'].T
    def infer(plan,x):
        raw=mx.concatenate([plan.encode(x,e) for e in ge],axis=1)
        z=(raw-gm['mean'])/gm['scale']
        f=mx.concatenate([z,(1+z@gm['centers'].T/z.shape[1])**2],axis=1)
        return raw,f@readout+bias
    compiled={}
    for k,plan in plans.items():
        fn=lambda x, plan=plan: infer(plan,x)
        compiled[k]=fn if a.eager else mx.compile(fn)
    mx.eval(readout,bias)
    start=time.perf_counter()
    packed={k:np.array([plans[k].gather(rows[i]['entry']) for i in ids],np.float32) for k,ids in groups.items()}
    gather_ms=(time.perf_counter()-start)*1000
    start=time.perf_counter()
    device={k:mx.array(x) for k,x in packed.items()};mx.eval(list(device.values()))
    upload_ms=(time.perf_counter()-start)*1000
    start=time.perf_counter()
    cpu_raw=np.array([np.concatenate([e(r['entry']) for e in encoders]) for r in rows])
    z=(cpu_raw-m['mean'])/m['scale']
    cpu=(features(z,str(m['kind']),m['centers'],m['projection'],m['bias'])@m['w']+m['b'])@m['codes'].T
    cpu_ms=(time.perf_counter()-start)*1000
    # First execution includes lazy kernel preparation; report independently.
    start=time.perf_counter(); outputs={k:compiled[k](x) for k,x in device.items()}
    mx.eval([v for pair in outputs.values() for v in pair]);cold_ms=(time.perf_counter()-start)*1000
    scores=np.zeros_like(cpu);raw=np.zeros_like(cpu_raw)
    start=time.perf_counter()
    for k,ids in groups.items():raw[ids]=np.array(outputs[k][0]);scores[ids]=np.array(outputs[k][1])
    download_ms=(time.perf_counter()-start)*1000
    np.testing.assert_allclose(raw,cpu_raw,atol=2e-5,rtol=2e-5)
    np.testing.assert_allclose(scores,cpu,atol=2e-3,rtol=2e-3)
    assert np.array_equal(scores.argmax(1),cpu.argmax(1))
    timings=[]
    for multiplier in (1,16,128):
        batches={k:mx.tile(x,(multiplier,1)) for k,x in device.items()};mx.eval(list(batches.values()))
        def execute():
            out=[compiled[k](x)[1] for k,x in batches.items()];mx.eval(out)
        execute();samples=[]
        for _ in range(a.repeat):
            start=time.perf_counter();execute();samples.append((time.perf_counter()-start)*1000)
        timings.append(dict(rows=len(rows)*multiplier,repeat_of_same_examples=multiplier,
                            median_gpu_encoding_and_ridge_ms=float(np.median(samples)),samples_ms=samples))
    pred=scores.argmax(1);labels=list(m['labels']);truth=np.array([labels.index(r['completion_key']) for r in rows])
    start=time.perf_counter();containment=[]
    for r,c in zip(rows,pred):containment.append(extension(r['entry'],catalog[labels[c]]) is not None)
    check_ms=(time.perf_counter()-start)*1000
    result=dict(scope='Standalone Metal GPU shared-layout encoding and fitted ridge completion recognition; no runtime effects',
        execution='eager' if a.eager else 'compiled-per-layout',
        gpu=str(mx.default_device()),mlx_version=mx.__version__ if hasattr(mx,'__version__') else 'see environment',
        test_rows=len(rows),layouts=len(plans),dynamic_scalar_values=sum(x.size for x in packed.values()),
        input_bytes=sum(x.nbytes for x in packed.values()),correct=int((pred==truth).sum()),
        cpu_gpu_argmax_equal=True,max_score_abs_error=float(np.max(abs(scores-cpu))),
        max_feature_abs_error=float(np.max(abs(raw-cpu_raw))),backpropagation=False,
        incorrect_passing_containment=int(sum(ok and p!=t for ok,p,t in zip(containment,pred,truth))),
        costs_ms=dict(layout_compilation=compile_ms,dynamic_gather=gather_ms,input_materialization=upload_ms,
          cold_gpu_encoding_and_ridge=cold_ms,output_materialization=download_ms,
          cpu_original_encoding_and_ridge=cpu_ms,necessary_containment_only=check_ms),batches=timings,
        lifecycle_cost=None,derivability_validation_cost=None,runtime_takeover=False,
        limitations=['export adapter, not direct Rust slot-reader integration','GPU input layouts derive from initial DAG only',
          'known completion catalog classification, not arbitrary generated saturation',
          'repeated batch rows measure throughput only; no additional test samples',
          'containment cannot authorize effects; lifecycle and derivability not implemented'],
        hashes={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ('corpus','model','catalog')})
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
