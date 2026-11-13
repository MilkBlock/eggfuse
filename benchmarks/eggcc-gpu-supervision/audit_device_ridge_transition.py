"""Real saved-input adapter audit; observed routes are not runtime matching."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from multi_entry_ridge import dataset,arrays,pooling,features
from device_ridge_transition import infer


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    start=time.monotonic();raw=read_bytes(a.trace);trace=json.loads(raw)
    if not all(trace.get(k) is True for k in ('strict_run_graphs_equal','strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('capture not audited')
    saved=np.load(a.model);channels=int(saved['channels']);encoding=str(saved['encoding'])
    model={k:saved[k] for k in ('w','coef')}
    nodes=dataset(trace,channels,bool(saved['zero_role_channels']),encoding);seed,q,target=arrays(nodes);n=len(nodes)
    state=dict(tokens=target,generation=np.ones(n,np.int32))
    for k in ('present','visible','settled'):state[k]=np.ones(n,bool)
    # Oracle completed states isolate direct consumption from accumulated error.
    # Incomplete captures remain boundary inputs as in the original experiment.
    state['token_dirty']=np.zeros(n,bool)
    preparation=time.monotonic()-start
    start=time.monotonic();expected=np.tanh(features(seed,q,pooling(nodes,target),model['w'],np)@model['coef']);reference=time.monotonic()-start
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);dev=lambda d:{k:mx.array(v) for k,v in d.items()}
    ds,dm=dev(state),dev(model);mx.eval(ds,dm)
    kernel=mx.compile(lambda s,r:infer(s,r,dm,mx))
    outputs=[];ready=[];seconds=0.;request_bytes=0;max_edges=0
    for begin in range(0,n,64):
        batch=nodes[begin:begin+64];b=len(batch);e=max(1,max(len(x['edges']) for x in batch));max_edges=max(max_edges,e)
        r=dict(seed=seed[begin:begin+b],q=q[begin:begin+b],sources=np.zeros((b,e),np.int32),generations=np.ones((b,e),np.int32),
            edge_valid=np.zeros((b,e),bool),edge=np.zeros((b,e,128),np.float32),route=np.zeros((b,e,channels),np.float32),input_ready=np.ones(b,bool))
        for j,node in enumerate(batch):
            for k,(src,edge) in enumerate(node['edges']):
                r['sources'][j,k]=src;r['edge'][j,k]=edge;r['route'][j,k]=node['edge_routes'][k];r['edge_valid'][j,k]=True
        request_bytes+=sum(v.nbytes for v in r.values());dr=dev(r);mx.eval(dr)
        start=time.monotonic();pred,marks=kernel(ds,dr);mx.eval(pred,marks);seconds+=time.monotonic()-start
        outputs.append(np.array(pred));ready.append(np.array(marks['ready']))
    actual=np.concatenate(outputs);delta=np.abs(actual-expected);valid=np.array([x['valid'] for x in nodes]);linked=np.array([x['linked'] for x in nodes])
    result=dict(scope='Saved-route, oracle-source audit of live-source ridge adapter; not autonomous execution',
        trace_sha256=hashlib.sha256(raw).hexdigest(),model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),encoding=encoding,
        cases=n,complete_cases=int(valid.sum()),linked_complete_cases=int((valid&linked).sum()),max_batch_edges=max_edges,
        request_bytes=request_bytes,preparation_seconds=preparation,cpu_reference_seconds=reference,
        gpu_seconds_including_compilation=seconds,max_absolute_difference=float(delta.max()),
        outside_tolerance=int((delta>(.002+.004*np.abs(expected))).sum()),all_ready=bool(np.concatenate(ready).all()),
        direct_linked_token_mse=float(np.mean((actual[valid&linked]-target[valid&linked])**2)),
        backpropagation=False,accuracy_gain_claimed=False,
        limitations=['Observed successful bindings and routes are oracle audit inputs',
                     'Source states include CPU boundary tokens for incomplete captures',
                     'No ownership transfer, saturation or committed mutation claim',
                     'Preparation excludes batch packing; timings are not end-to-end throughput'])
    result['passed']=result['all_ready'] and result['outside_tolerance']==0 and bool(np.isfinite(actual).all())
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
