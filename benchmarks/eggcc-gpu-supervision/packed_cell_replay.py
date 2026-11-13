"""Static degree groups for Cell aggregation, with one ridge readout per layer.

No model fit, matching, rule selection, or GPU-side variable control flow.
"""
import argparse
from collections import defaultdict
import hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from multi_entry_ridge import WIDTH,arrays,dataset,features,replay
from collect_observed_corpus import read_bytes
from audit_multi_entry_dynamics import train_catalog,evaluate


def prepare(nodes,packed,selected_ids=None):
    channels=nodes[0].get('edge_width',WIDTH)//WIDTH;layers=defaultdict(list);result=[]
    selected=enumerate(nodes) if selected_ids is None else ((i,nodes[i]) for i in sorted(selected_ids))
    for i,n in selected:
        if not n['valid']:continue
        for source,_ in n['edges']:
            if not 0<=source<len(nodes):raise ValueError('source outside state array')
            if nodes[source]['valid'] and nodes[source]['depth']>=n['depth']:
                raise ValueError('unproved layer independence')
        layers[n['depth']].append(i)
    for depth,ids in sorted(layers.items()):
        if packed=='two':
            positive=sorted((i for i in ids if nodes[i]['edges']),key=lambda i:len(nodes[i]['edges']))
            buckets={0:[i for i in ids if not nodes[i]['edges']]}
            if positive:
                counts=[len(nodes[i]['edges']) for i in positive];n=len(positive)
                cuts=[k for k in range(1,n) if counts[k-1]!=counts[k]]+[n]
                cut=min(cuts,key=lambda k:k*counts[k-1]+(n-k)*counts[-1])
                buckets[1]=positive[:cut];buckets[2]=positive[cut:]
            buckets={k:v for k,v in buckets.items() if v}
        else:
            buckets=defaultdict(list)
            for i in ids:
                count=len(nodes[i]['edges'])
                key=0 if not count else (1+(count-1).bit_length() if packed else 1)
                buckets[key].append(i)
        groups=[];ordered=[]
        for _,members in sorted(buckets.items()):
            width=max(len(nodes[i]['edges']) for i in members)
            sources=np.zeros((len(members),width),np.int32)
            base=np.zeros((len(members),width,WIDTH),np.float32)
            route=np.zeros((len(members),width,channels),np.float32)
            for j,i in enumerate(members):
                edges=nodes[i]['edges'];normalizer=np.sqrt(max(1,len(edges)))
                routes=nodes[i].get('edge_routes')
                if routes is None:routes=np.ones((len(edges),channels),np.float32)
                for k,(source,v) in enumerate(edges):
                    sources[j,k]=source;base[j,k]=v/normalizer
                    route[j,k]=routes[k]
            groups.append(dict(sources=sources,base=base,route=route,rows=len(members)))
            ordered.extend(members)
        result.append(dict(ids=np.array(ordered,np.int32),groups=groups,depth=depth))
    return result


def prepare_shared(nodes,min_rows=8):
    """At most one shared layout per layer, plus two residual degree groups.

    Compare exact float32 coefficient bytes, never source IDs or state values.
    The admission test is lower stored bytes, not a prediction of speedup.
    """
    plan=prepare(nodes,'two');channels=nodes[0].get('edge_width',WIDTH)//WIDTH;intern={}
    for layer_index,layer in enumerate(plan):
        matches=defaultdict(list)
        for i in layer['ids']:
            n=nodes[i];edges=n['edges']
            if not edges:continue
            base=np.array([v/np.sqrt(len(edges)) for _,v in edges],np.float32)
            routes=n.get('edge_routes')
            route=np.array(routes,np.float32) if routes is not None else np.ones((len(edges),channels),np.float32)
            key=(len(edges),base.tobytes(),route.tobytes())
            matches[key].append(int(i))
        candidates=[(key,ids) for key,ids in matches.items() if len(ids)>=min_rows]
        if not candidates:continue
        key,members=max(candidates,key=lambda item:((len(item[1])-1)*item[0][0],-item[1][0]))
        base=np.frombuffer(key[1],np.float32).reshape(1,key[0],WIDTH)
        route=np.frombuffer(key[2],np.float32).reshape(1,key[0],channels)
        sources=np.array([[src for src,_ in nodes[i]['edges']] for i in members],np.int32)
        shared=dict(sources=sources,base=base,route=route,rows=len(members),shared=True)
        remaining=set(map(int,layer['ids']))-set(members)
        residual=prepare(nodes,'two',remaining) if remaining else []
        assert len(residual)<=1
        groups=[shared]+(residual[0]['groups'] if residual else [])
        before=sum(g['base'].nbytes+g['route'].nbytes for g in layer['groups'])
        after=sum(g['base'].nbytes+g['route'].nbytes for g in groups)
        if after>=before:continue
        # Reuse exact static matrices across layers without a device-side table.
        shared['base'],shared['route']=intern.setdefault(key,(base,route))
        ids=members+(residual[0]['ids'].tolist() if residual else [])
        plan[layer_index]=dict(ids=np.array(ids,np.int32),groups=groups,depth=layer['depth'])
    return plan


def prepare_broadcast(nodes):
    """Share whole existing coefficient rows without adding aggregation groups."""
    plan=prepare(nodes,'two');intern={}
    for layer in plan:
        for group in layer['groups']:
            for name in ('base','route'):
                value=group[name]
                if value.shape[0]>1 and value.size and np.array_equal(value,np.broadcast_to(value[:1],value.shape)):
                    value=value[:1].copy()  # Do not retain the expanded backing array.
                    group['shared']=True
                key=(value.shape,value.tobytes())
                group[name]=intern.setdefault(key,value)
    return plan


def costs(plan):
    groups=[g for layer in plan for g in layer['groups']]
    unique={id(g[k]):g[k] for g in groups for k in ('base','route')}
    return dict(unique_coefficient_bytes=sum(v.nbytes for v in unique.values()),
        shared_groups=sum(bool(g.get('shared')) for g in groups),
        shared_rows=sum(g['rows'] for g in groups if g.get('shared')),
        layers=len(plan),readouts=len(plan),aggregation_groups=sum(g['sources'].shape[1]>0 for g in groups),
        zero_input_groups=sum(g['sources'].shape[1]==0 for g in groups),
        padded_edges=sum(g['sources'].size for g in groups),
        coefficient_bytes=sum(g['base'].nbytes+g['route'].nbytes for g in groups),
        source_index_bytes=sum(g['sources'].nbytes for g in groups),
        destination_index_bytes=sum(layer['ids'].nbytes for layer in plan),
        peak_layer_coefficient_bytes=max((sum(g['base'].nbytes+g['route'].nbytes for g in layer['groups']) for layer in plan),default=0))


def executor(nodes,w,coef,plan,gpu):
    xp=mx if gpu else np;seed,q,target=arrays(nodes);channels=nodes[0].get('edge_width',WIDTH)//WIDTH
    valid=np.array([n['valid'] for n in nodes]);initial=xp.array(np.where(valid[:,None],0,target),dtype=xp.float32)
    seed,q,w,coef=[xp.array(a) for a in (seed,q,w,coef)]
    constants={}
    def constant(array):
        key=id(array)
        if key not in constants:constants[key]=xp.array(array)
        return constants[key]
    def make_step(layer):
        ids=xp.array(layer['ids']);groups=[(g['rows'],xp.array(g['sources']),constant(g['base']),constant(g['route'])) for g in layer['groups']]
        def step(state):
            chunks=[]
            for rows,sources,base,route in groups:
                if sources.shape[1]==0:  # Static shape, not a device-side branch.
                    chunks.append(xp.zeros((rows,channels*WIDTH),dtype=xp.float32))
                else:
                    chunks.append(xp.matmul(xp.swapaxes(route,1,2),state[sources]*base).reshape(rows,channels*WIDTH))
            pool=xp.concatenate(chunks,axis=0)
            out=xp.tanh(features(seed[ids],q[ids],pool,w,xp)@coef)
            if gpu:return state.at[ids].add(out)
            result=state.copy();result[ids]=out;return result
        return mx.compile(step) if gpu else step
    steps=[make_step(layer) for layer in plan]
    def run():
        state=initial
        for step in steps:state=step(state)
        if gpu:mx.eval(state)
        return state
    return run


def audit(a,b):
    finite=bool(np.isfinite(a).all() and np.isfinite(b).all())
    outside=int(np.count_nonzero(abs(a-b)>.002+.004*abs(b)))
    return dict(passed=finite and outside==0,finite=finite,outside=outside,max_abs=float(np.max(abs(a-b))))


def main():
    p=argparse.ArgumentParser();p.add_argument('training',type=Path);p.add_argument('test_trace',type=Path)
    p.add_argument('model',type=Path);p.add_argument('model_report',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    report=json.loads(a.model_report.read_text());raw=read_bytes(a.test_trace);manifest_raw=a.training.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=report['provenance']['test_trace']:raise ValueError('trace mismatch')
    if hashlib.sha256(manifest_raw).hexdigest()!=report['provenance']['train']:raise ValueError('training mismatch')
    if hashlib.sha256(a.model.read_bytes()).hexdigest()!=report['model_sha256']:raise ValueError('model mismatch')
    with np.load(a.model) as saved:w=saved['w'];coef=saved['coef'];channels=int(saved['channels']);zero=bool(saved['zero_role_channels'])
    nodes=dataset(json.loads(raw),channels,zero);predictions={};runs={}
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu)
    for name,packed in [('flat',False),('packed',True),('two_groups','two'),('shared','shared'),('broadcast','broadcast')]:
        started=time.monotonic();plan=prepare_broadcast(nodes) if packed=='broadcast' else prepare_shared(nodes) if packed=='shared' else prepare(nodes,packed);plan_seconds=time.monotonic()-started
        started=time.monotonic();run=executor(nodes,w,coef,plan,True);setup_seconds=time.monotonic()-started
        started=time.monotonic();cold=run();cold_seconds=time.monotonic()-started
        started=time.monotonic();warm=run();warm_seconds=time.monotonic()-started
        # Only final states leave GPU; the second invocation also tests plan reuse.
        predictions[name]=np.array(warm);repeat_audit=audit(np.array(cold),predictions[name])
        started=time.monotonic();cpu_run=executor(nodes,w,coef,plan,False);cpu_setup=time.monotonic()-started
        started=time.monotonic();cpu=cpu_run();cpu_seconds=time.monotonic()-started
        runs[name]=dict(costs=costs(plan),plan_seconds=plan_seconds,gpu_setup_seconds=setup_seconds,
            gpu_cold_seconds=cold_seconds,gpu_second_call_seconds=warm_seconds,
            cpu_setup_seconds=cpu_setup,cpu_execute_seconds=cpu_seconds,
            numeric_audit=audit(predictions[name],cpu),reused_plan_audit=repeat_audit)
    reference=replay(nodes,w,coef,False)
    manifest=json.loads(manifest_raw);training=[]
    if manifest['partition']!='train':raise ValueError('training partition required')
    for e in manifest['cases']:
        if e['status']!='complete':continue
        if e['split']!='train':raise ValueError('case partition mismatch')
        data=read_bytes(Path(e['trace']))
        if hashlib.sha256(data).hexdigest()!=e['trace_sha256']:raise ValueError('training trace mismatch')
        training.extend(dataset(json.loads(data),channels,zero))
    predictions['original']=reference
    result=dict(scope='frozen-model packed GPU Cell replay; observed routing, no autonomous matching',
        model_sha256=report['model_sha256'],test_trace_sha256=report['provenance']['test_trace'],runs=runs,
        broadcast_vs_original=audit(predictions['broadcast'],reference),
        shared_vs_original=audit(predictions['shared'],reference),
        two_groups_vs_original=audit(predictions['two_groups'],reference),
        packed_vs_original=audit(predictions['packed'],reference),flat_vs_original=audit(predictions['flat'],reference),
        recovery=evaluate(nodes,predictions,train_catalog(training))['train_dictionary_decode'],
        intermediate_cpu_state_reads=0,backpropagation=False,
        limitations=['Two diagnostic calls per plan, not a throughput campaign',
            'Flat control also eliminates zero-edge gather; original comparison is reported separately',
            'Only admitted exact coefficient rows are shared; other rows remain duplicated',
            'No coverage, ownership, matching or saturation improvement'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not all(r['numeric_audit']['passed'] and r['reused_plan_audit']['passed'] for r in runs.values()) or not result['packed_vs_original']['passed'] or not result['flat_vs_original']['passed'] or not result['two_groups_vs_original']['passed'] or not result['shared_vs_original']['passed'] or not result['broadcast_vs_original']['passed']:raise SystemExit(1)

if __name__=='__main__':main()
