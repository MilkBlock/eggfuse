"""Real saved-input adapter audit; observed routes are not runtime matching."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from multi_entry_ridge import dataset,arrays,pooling,features
from device_ridge_transition import infer
from ridge_request_layout import group_layouts,pack_audit_requests


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path);p.add_argument('--shared-layouts',action='store_true');p.add_argument('--bucket-layouts',action='store_true');a=p.parse_args()
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
    shared_kernel=mx.compile(lambda s,r,l:infer(s,r,dm,mx,l))
    warm_seconds=0.
    outputs=np.zeros_like(target);ready=np.zeros(n,bool);seconds=0.;request_bytes=0;max_edges=0;layout_bytes=0
    packing_start=time.monotonic()
    groups=group_layouts(nodes,channels) if a.shared_layouts or a.bucket_layouts else None
    grouping_seconds=time.monotonic()-packing_start
    jobs=[]
    if a.bucket_layouts:
        buckets={}
        for layout in groups:
            width=1<<(layout['edge'].shape[1]-1).bit_length()
            buckets.setdefault(width,[]).append(layout)
        for width,layouts in buckets.items():
            edge=np.zeros((len(layouts),width,128),np.float32);route=np.zeros((len(layouts),width,channels),np.float32)
            records=[]
            for lid,layout in enumerate(layouts):
                e=layout['edge'].shape[1];edge[lid,:e]=layout['edge'][0];route[lid,:e]=layout['route'][0]
                records.extend((i,lid) for i in layout['indices'])
            records.sort()
            dl=dev(dict(edge=edge,route=route));mx.eval(dl);layout_bytes+=edge.nbytes+route.nbytes
            for begin in range(0,len(records),64):
                batch=records[begin:begin+64];ids=[i for i,_ in batch];b=len(ids)
                r=dict(seed=seed[ids],q=q[ids],sources=np.zeros((b,width),np.int32),generations=np.ones((b,width),np.int32),
                       edge_valid=np.zeros((b,width),bool),input_ready=np.ones(b,bool),layout_index=np.array([lid for _,lid in batch],np.int32))
                for row,i in enumerate(ids):
                    count=len(nodes[i]['edges']);r['sources'][row,:count]=[src for src,_ in nodes[i]['edges']];r['edge_valid'][row,:count]=True
                jobs.append((ids,r,dl))
    elif groups is not None:
        for layout in groups:
            dl=dev({k:layout[k] for k in ('edge','route')});mx.eval(dl)
            layout_bytes+=layout['edge'].nbytes+layout['route'].nbytes
            for begin in range(0,len(layout['indices']),64):
                ids=layout['indices'][begin:begin+64]
                jobs.append((ids,pack_audit_requests(nodes,ids,seed,q,layout),dl))
    else:
        for begin in range(0,n,64):
            batch=nodes[begin:begin+64];b=len(batch);e=max(1,max(len(x['edges']) for x in batch))
            r=dict(seed=seed[begin:begin+b],q=q[begin:begin+b],sources=np.zeros((b,e),np.int32),generations=np.ones((b,e),np.int32),
                edge_valid=np.zeros((b,e),bool),edge=np.zeros((b,e,128),np.float32),route=np.zeros((b,e,channels),np.float32),input_ready=np.ones(b,bool))
            for j,node in enumerate(batch):
                for k,(src,edge) in enumerate(node['edges']):
                    r['sources'][j,k]=src;r['edge'][j,k]=edge;r['route'][j,k]=node['edge_routes'][k];r['edge_valid'][j,k]=True
            jobs.append((list(range(begin,begin+b)),r,None))
    packing_seconds=time.monotonic()-packing_start
    for ids,r,dl in jobs:
        max_edges=max(max_edges,r['sources'].shape[1]);request_bytes+=sum(v.nbytes for v in r.values());dr=dev(r);mx.eval(dr)
        start=time.monotonic()
        pred,marks=kernel(ds,dr) if dl is None else shared_kernel(ds,dr,dl)
        mx.eval(pred,marks);seconds+=time.monotonic()-start
        outputs[ids]=np.array(pred);ready[ids]=np.array(marks['ready'])
        durations=[]
        for _ in range(3):
            start=time.monotonic()
            wp,wm=kernel(ds,dr) if dl is None else shared_kernel(ds,dr,dl)
            mx.eval(wp,wm);durations.append(time.monotonic()-start)
        warm_seconds+=min(durations)
    actual=outputs;delta=np.abs(actual-expected);valid=np.array([x['valid'] for x in nodes]);linked=np.array([x['linked'] for x in nodes])
    result=dict(scope='Saved-route, oracle-source audit of live-source ridge adapter; not autonomous execution',
        trace_sha256=hashlib.sha256(raw).hexdigest(),model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),encoding=encoding,
        cases=n,complete_cases=int(valid.sum()),linked_complete_cases=int((valid&linked).sum()),max_batch_edges=max_edges,
        shared_layouts=a.shared_layouts or a.bucket_layouts,bucket_layouts=a.bucket_layouts,layout_count=len(groups) if groups is not None else 0,
        layout_bytes=layout_bytes,request_bytes=request_bytes,total_input_bytes=layout_bytes+request_bytes,
        batches=len(jobs),grouping_seconds=grouping_seconds,packing_seconds_including_layout_upload=packing_seconds,preparation_seconds=preparation,cpu_reference_seconds=reference,
        gpu_seconds_including_compilation=seconds,gpu_sum_per_batch_min_of_three_warm_seconds=warm_seconds,max_absolute_difference=float(delta.max()),
        outside_tolerance=int((delta>(.002+.004*np.abs(expected))).sum()),all_ready=bool(ready.all()),
        direct_linked_token_mse=float(np.mean((actual[valid&linked]-target[valid&linked])**2)),
        backpropagation=False,accuracy_gain_claimed=False,
        limitations=['Observed successful bindings and routes are oracle audit inputs',
                     'Source states include CPU boundary tokens for incomplete captures',
                     'No ownership transfer, saturation or committed mutation claim',
                     'Dynamic upload/readback not timed; timings are not end-to-end throughput'])
    result['passed']=result['all_ready'] and result['outside_tolerance']==0 and bool(np.isfinite(actual).all())
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
