"""Same-input cached multi-row emission latency and complete-batch throughput."""
import argparse,json,time,statistics,hashlib
from pathlib import Path
import numpy as np
import mlx.core as mx
from stream_model import StreamGenerator
from stream_metrics import check_token
from data import features,coordinates,audit,N,Q
from model import decode,verify


def exact(a,b,sp):
    equality=a[:,:,0,None]==b[:,None,:,0]
    order=mx.argsort(mx.where(equality.reshape(-1,N*N),mx.arange(N*N),N*N),axis=-1)[:,:Q]
    i=order//N;j=order%N;active=mx.take_along_axis(equality.reshape(-1,N*N),order,axis=1).astype(mx.int32)
    aa=mx.take_along_axis(a,i[...,None],1);bb=mx.take_along_axis(b,j[...,None],1)
    return dict(active=active,pointers=mx.stack((i,j),-1),fields=mx.stack((aa[...,0],aa[...,1],bb[...,1]),-1),addresses=mx.stack((sp[i],sp[N+j]),-2))


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);models={};metadata={}
    for path in sorted(a.root.iterdir()):
        if not (path/'result.json').exists():continue
        key=path.name;r=json.loads((path/'result.json').read_text());arm=r['protocol']['arm']
        assert hashlib.sha256((path/'model.safetensors').read_bytes()).hexdigest()==r['model_sha256']
        model=StreamGenerator(arm);model.load_weights(str(path/'model.safetensors'));mx.eval(model.parameters());models[key]=model;metadata[key]=r['model_sha256']
    assert len(models)==4
    results={}
    for panel in ('iid','triple_right','four_right'):
        for rows,length in ((4,2),(2,4)):
            name=f'{panel}-{rows}x{length}'
            with np.load(a.root/'feedback-1703'/f'{name}.npz') as z:aa=z['a'][:32];bb=z['b'][:32]
            sp,op=map(mx.array,coordinates(rows,length));functions={}
            for key,m in models.items():
                def f(x,ia,ib,m=m):
                    raw=m(x,sp,op,rows,length);out={**raw,**decode(raw,sp)};check=verify(ia,ib,out)
                    return out,check&mx.all(mx.isfinite(raw['latent']),axis=(1,2))&mx.all(mx.isfinite(raw['field_logits']),axis=(1,2))
                functions[key]=mx.compile(f)
            def deterministic(x,ia,ib):
                out=exact(ia,ib,sp);return out,verify(ia,ib,out)
            functions['exact_gpu']=mx.compile(deterministic)
            def inputs(i):return mx.array(features(aa[i:i+1],bb[i:i+1])),mx.array(aa[i:i+1]),mx.array(bb[i:i+1])
            for f in functions.values():
                for i in range(4):mx.eval(f(*inputs(i)))
            samples={k:[] for k in functions};outputs={k:[] for k in functions};names=list(functions)
            for i in range(32):
                for k in names[i%len(names):]+names[:i%len(names)]:
                    start=time.perf_counter();out=functions[k](*inputs(i));mx.eval(out);samples[k].append((time.perf_counter()-start)*1000);outputs[k].append(out)
            records={}
            for k in names:
                decoded={field:np.concatenate([np.array(out[field]) for out,_ in outputs[k]]) for field in outputs[k][0][0]}
                if k!='exact_gpu':check_token(decoded,np.array(sp))
                r=audit(aa,bb,decoded,np.array(sp));assert r['complete_graphs']==sum(bool(np.array(p)[0]) for _,p in outputs[k])
                records[k]=dict(audit=r,host_median_ms=statistics.median(samples[k]),samples_ms=samples[k],complete_graphs_per_second=r['complete_graphs']/(sum(samples[k])/1000))
            results[name]=records;print(name,{k:(r['audit']['complete_graphs'],round(r['host_median_ms'],3)) for k,r in records.items()},flush=True)
    r=dict(results=results,model_sha256=metadata,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='one semantic stage; 8 output slots; 4x2 uses two causal rounds, 2x4 uses four; B=1; input preparation+GPU generation+verification timed; CPU post-audit excluded',
        exact_baseline='GPU equality matrix plus fixed-capacity packing, no neural model; source contract has at most 8 obligations',
        note='No neural speedup claim is valid when completeness differs. Exact GPU baseline pays identical feature construction for conservative comparison.')
    a.output.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':main()
