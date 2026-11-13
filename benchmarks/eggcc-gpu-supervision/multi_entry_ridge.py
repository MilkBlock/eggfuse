"""Actual multi-provider Cell token replay: closed-form ridge, fixed GPU layers.

Observed matches and wiring are supplied, not predicted. Output codes encode
local slot roles, scalar values and Eq partitions, never numeric node IDs.
"""
import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from whole_cell_ridge import code,train
from collect_observed_corpus import read_bytes
from link_rhs_results import link

WIDTH=128

@lru_cache(maxsize=None)
def vector(text):return code(json.loads(text))
def vec(x):return vector(json.dumps(x,sort_keys=True))


def template(rule):
    roles=defaultdict(list)
    for side,ops in [('query',rule['query']),('effect',rule['effects'])]:
        for op in ops:
            label=(side,op.get('kind','query'),op.get('call',{}))
            for i,arg in enumerate(op.get('args',[])):
                if 'slot' in arg:roles[arg['slot']].append((label,i))
            if 'dst' in op:roles[op['dst']].append((label,'out'))
            for field in ('arg','value'):
                if 'slot' in op.get(field,{}):roles[op[field]['slot']].append((label,field))
    vectors=[np.tanh(sum((vec(r) for r in roles[i]),np.zeros(64,np.float32))+vec(('sort',s['sort'])))
             for i,s in enumerate(rule['slots'])]
    request=np.tanh(sum(vectors,np.zeros(64,np.float32))/np.sqrt(max(1,len(vectors))))
    return np.array(vectors,np.float32),request


def neighborhood_template(rule,rounds=2):
    """Bake neighboring operand roles/literals; never read instance outcomes."""
    base,_=template(rule);state=base.copy();operations=[]
    for side,ops in [('query',rule['query']),('effect',rule['effects'])]:
        for op in ops:
            operands=[(str(i),a) for i,a in enumerate(op.get('args',[]))]
            operands += [(key,op[key]) for key in ('arg','value') if key in op]
            if 'dst' in op:operands.append(('out',dict(slot=op['dst'])))
            label=(side,op.get('kind','query'),op.get('call',{}))
            operations.append((label,operands))
    for _ in range(rounds):
        messages=[[] for _ in rule['slots']]
        for label,operands in operations:
            parts=[np.tanh((state[a['slot']] if 'slot' in a else vec(('literal-operand',a)))+vec(('position',pos))) for pos,a in operands]
            context=np.tanh(vec(label)+sum(parts,np.zeros(64,np.float32))/np.sqrt(max(1,len(parts))))
            for pos,a in operands:
                if 'slot' in a:messages[a['slot']].append(np.tanh(context+vec(('position',pos))))
        state=np.array([np.tanh(base[i]+sum(m,np.zeros(64,np.float32))/np.sqrt(max(1,len(m)))) for i,m in enumerate(messages)],np.float32)
    request=np.tanh(state.sum(0)/np.sqrt(max(1,len(state)))) if len(state) else np.zeros(64,np.float32)
    return state,request


def scalar(value):
    # Values remain dynamic floating inputs; strings/categories use a fixed code.
    raw=value.get('value')
    if isinstance(raw,(float,int)) and not isinstance(raw,bool):
        n=float(raw)
        if np.isfinite(n):
            x=np.sign(n)*np.log1p(abs(n))
            return np.tanh(x*vec(('numeric',value.get('sort'))))
    return vec(('scalar',value))


def encode(rows,roles,encoding="slot"):
    if encoding not in ("slot","class-balanced","class-interface","class-history","class-history-split","class-history-repeat","class-history-fallback","class-history-earliest","class-history-neighborhood","class-history-neighborhood-input"):raise ValueError("unknown token encoding")
    groups=defaultdict(list)
    for slot,value,key in rows:
        if key is not None:groups[key].append(slot)
    context={k:roles[slots].sum(0)/(len(slots) if encoding!="slot" else np.sqrt(len(slots))) for k,slots in groups.items()}
    messages=[]
    for slot,value,key in rows:
        messages.append(np.tanh(roles[slot]+(context[key] if key is not None else scalar(value))))
    if not messages:return np.zeros(WIDTH,np.float32)
    m=np.array(messages,np.float32)
    if encoding!="slot":
        # Each observed Eq class has unit total weight; scalars remain individual.
        # Input groups use only input roots; output groups are training/audit labels.
        weights=np.array([1/len(groups[key]) if key is not None else 1 for _,_,key in rows],np.float32)
        count=weights.sum()
        first=(m*weights[:,None]).sum(0)/np.sqrt(count)
        second=(m*m*weights[:,None]).sum(0)/count
    else:first=m.sum(0)/np.sqrt(len(m));second=(m*m).mean(0)
    return np.tanh(np.concatenate([first,second])).astype(np.float32)


def input_rows(binding):
    ports={p['slot']:(p['sort'],p['before']) for p in binding['eq_ports']}
    return [(s['slot'],s['value'],ports.get(s['slot'])) for s in binding['values']]


def input_seed(binding,roles,connected,encoding):
    # Connected Eq slots still carry interface correlations between providers.
    rows=input_rows(binding)
    return encode([r for r in rows if encoding in ('class-interface','class-history','class-history-split','class-history-repeat','class-history-fallback','class-history-earliest','class-history-neighborhood','class-history-neighborhood-input') or r[0] not in connected],roles,encoding)


def output_rows(binding):
    return [(s['slot'],s['value'],(s['eq_port']['sort'],s['eq_port']['after_run']) if 'eq_port' in s else None)
            for s in binding['rhs']['slots'] if 'unavailable' not in s]


def state_key(rows):
    classes={};out=[]
    for slot,value,key in sorted(rows,key=lambda r:r[0]):
        if key is None:out.append((slot,value))
        else:out.append((slot,dict(sort=key[0],local_class=classes.setdefault(key,len(classes)))))
    return json.dumps(out,sort_keys=True)


def encoding_audit(nodes):
    groups=defaultdict(set);members=Counter()
    for n in nodes:
        if not n['valid']:continue
        key=n['target'].tobytes();groups[key].add(n['state_key']);members[key]+=1
    bad={k for k,v in groups.items() if len(v)>1}
    return dict(distinct_codes=len(groups),conflicting_codes=len(bad),
                instances_in_conflicting_codes=sum(members[k] for k in bad))


def template_identity(rule):
    # Exact static layout/operations, including literals; no runtime IDs or rule names.
    structural=dict(query=rule['query'],effects=rule['effects'],sorts=[s['sort'] for s in rule['slots']])
    return hashlib.sha256(json.dumps(structural,sort_keys=True).encode()).hexdigest()


def context_route(route,historical,encoding):
    if encoding=='class-history-split':
        zero=np.zeros_like(route)
        return np.concatenate([zero,route] if historical else [route,zero])
    if encoding=='class-history-repeat':return np.concatenate([route,route])/np.sqrt(2)
    return route


def dataset(trace,channels=1,zero_role_channels=False,encoding="slot"):
    if not 1<=channels<=8:raise ValueError("channel count outside experiment limits")
    separated=encoding in ('class-history-split','class-history-repeat')
    if separated and channels!=8:raise ValueError('context comparison requires eight channels')
    role_channels=4 if separated else channels
    routing=np.random.default_rng(777).normal(0,1/np.sqrt(128),(128,role_channels-1)).astype(np.float32)
    if encoding.startswith('class-history'):
        from historical_cell_sources import link_history
        links=link_history(trace,fallback_only=encoding in ('class-history-fallback','class-history-earliest','class-history-neighborhood','class-history-neighborhood-input'),earliest=encoding in ('class-history-earliest','class-history-neighborhood','class-history-neighborhood-input'))
    else:links=link(trace)
    targets=[template(r) for r in trace['recipe']['rules']]
    neighborhoods=[neighborhood_template(r) for r in trace['recipe']['rules']] if encoding in ('class-history-neighborhood','class-history-neighborhood-input') else None
    compiled=neighborhoods if encoding=='class-history-neighborhood' else targets
    families=[template_identity(r) for r in trace['recipe']['rules']]
    nodes=[];addresses={};by_consumer={}
    for w in links['windows']:
        for c in w['consumers']:by_consumer[(w['consumer_run'],c['binding'])]=(w,c)
    for run in trace['runs']:
        for ordinal,b in enumerate(run['audit']['bindings']):
            idx=len(nodes);address=(run['ordinal'],ordinal);roles,q=compiled[b['rule']]
            incoming=[];routes=[];connected=set()
            if address in by_consumer:
                w,c=by_consumer[address]
                for port in c['ports']:
                    if 'group' not in port:continue
                    connected.add(port['slot']);g=w['groups'][port['group']]
                    # Preserve alternatives; no unique producer or owner is inferred.
                    for p in g['providers']:
                        source=addresses[(p.get('run',w['producer_run']),p['binding'])]
                        pr,_=compiled[p['rule']]
                        edge=np.concatenate([np.tanh(roles[port['slot']]+pr[p['slot']]),
                                             np.tanh(roles[port['slot']]-pr[p['slot']])])
                        route=np.concatenate([np.ones(1,np.float32),np.tanh(3*np.concatenate([roles[port['slot']],pr[p['slot']]])@routing)])
                        if zero_role_channels:route[1:]=0
                        route=context_route(route,port.get('relation')=='historical_observed_identity',encoding)
                        incoming.append((source,edge/np.sqrt(len(g['providers']))));routes.append(route)
            seed=input_seed(b,roles,connected,encoding)
            if encoding=='class-history-neighborhood-input':
                nr,nq=neighborhoods[b['rule']]
                q=np.concatenate([q,input_seed(b,nr,connected,encoding),nq])
            target=encode(output_rows(b),targets[b['rule']][0],encoding)
            valid=b['rhs']['completed'] and all('unavailable' not in s for s in b['rhs']['slots'])
            # A missing full local state is an explicit CPU boundary in this probe.
            depth=1+max((nodes[i]['depth'] for i,_ in incoming),default=-1)
            nodes.append(dict(seed=seed,q=q,target=target,edges=incoming,edge_routes=routes,edge_width=channels*WIDTH,depth=depth,valid=valid,
                              linked=bool(incoming),multiple=len({i for i,_ in incoming})>1,state_key=state_key(output_rows(b)),family=families[b['rule']]))
            addresses[address]=idx
    return nodes


def arrays(nodes):
    return [np.array([n[k] for n in nodes],np.float32) for k in ('seed','q','target')]


def pooling(nodes,states):
    width=nodes[0].get("edge_width",WIDTH);channels=width//WIDTH
    result=np.zeros((len(nodes),width),np.float32)
    for j,n in enumerate(nodes):
        if n['edges']:
            routes=n.get('edge_routes',[np.ones(channels,np.float32) for _ in n['edges']])
            messages=np.array([states[i]*w for i,w in n['edges']],np.float32)
            result[j]=(np.array(routes).T@messages).reshape(-1)/np.sqrt(len(n['edges']))
    return result


def features(seed,q,pool,w,xp):
    repeated=xp.concatenate([seed]*(pool.shape[1]//WIDTH),axis=1)
    raw=xp.concatenate([seed,q,pool,repeated*pool],axis=1)
    return xp.concatenate([xp.ones((len(seed),1),dtype=xp.float32),raw,xp.tanh(raw@w)],axis=1)


def replay(nodes,w,coef,gpu):
    xp=mx if gpu else np;seed,q,target=arrays(nodes)
    channels=nodes[0].get("edge_width",WIDTH)//WIDTH
    # Incomplete captures are CPU boundary tokens, explicitly counted in results.
    state=xp.array(np.where(np.array([n['valid'] for n in nodes])[:,None],0,target),dtype=xp.float32)
    s,q=xp.array(seed),xp.array(q);weights,coeff=xp.array(w),xp.array(coef)
    for depth in range(max(n['depth'] for n in nodes)+1):
        ids=[i for i,n in enumerate(nodes) if n['depth']==depth and n['valid']]
        if not ids:continue
        width=max(1,max(len(nodes[i]['edges']) for i in ids))
        sources=np.zeros((len(ids),width),np.int32);edge=np.zeros((len(ids),width,WIDTH),np.float32);route=np.zeros((len(ids),width,channels),np.float32)
        for j,i in enumerate(ids):
            for k,(source,v) in enumerate(nodes[i]['edges']):
                sources[j,k]=source;edge[j,k]=v/np.sqrt(len(nodes[i]['edges']))
                route[j,k]=nodes[i].get('edge_routes',[np.ones(channels,np.float32) for _ in nodes[i]['edges']])[k]
        ii=xp.array(np.array(ids,np.int32));src=xp.array(sources);ew=xp.array(edge);rw=xp.array(route)
        def step(current,ii,src,ew,rw):
            pool=xp.matmul(xp.swapaxes(rw,1,2),current[src]*ew).reshape(len(ii),channels*WIDTH)
            values=xp.tanh(features(s[ii],q[ii],pool,weights,xp)@coeff)
            if gpu:return current.at[ii].add(values)
            updated=current.copy();updated[ii]=values;return updated
        state=(mx.compile(step) if gpu else step)(state,ii,src,ew,rw)
    if gpu:mx.eval(state)
    return np.array(state)


def layout_costs(nodes):
    channels=nodes[0].get('edge_width',WIDTH)//WIDTH
    layers=defaultdict(list)
    for n in nodes:
        if n['valid']:layers[n['depth']].append(n)
    padded=[len(rows)*max(1,max(len(n['edges']) for n in rows)) for rows in layers.values()]
    total=sum(padded)
    return dict(channels=channels,padded_edge_slots=total,peak_layer_edge_slots=max(padded,default=0),
        padded_base_coefficient_bytes=total*WIDTH*4,padded_route_coefficient_bytes=total*channels*4,
        expanded_padded_coefficient_bytes=total*channels*WIDTH*4,
        padded_source_index_bytes=total*4,instance_state_bytes=len(nodes)*WIDTH*4,
        scope='cumulative arrays prepared across layers; excludes model, Python objects and allocator temporaries')


def metric(pred,target,mask):
    d=(pred[mask]-target[mask]).astype(np.float64)
    return dict(cases=int(mask.sum()),rmse=float(np.sqrt(np.mean(d*d))) if mask.any() else None,
                max_abs=float(np.max(np.abs(d))) if mask.any() else None)


def main():
    p=argparse.ArgumentParser();p.add_argument('training',type=Path);p.add_argument('validation',type=Path)
    p.add_argument('test_trace',type=Path);p.add_argument('model',type=Path);p.add_argument('report',type=Path);p.add_argument('--corpus-manifest',type=Path,required=True);p.add_argument('--channels',type=int,default=1);p.add_argument('--zero-role-channels',action='store_true');p.add_argument('--encoding',choices=['slot','class-balanced','class-interface','class-history','class-history-split','class-history-repeat','class-history-fallback','class-history-earliest','class-history-neighborhood','class-history-neighborhood-input'],default='slot');a=p.parse_args()
    preparation_started=time.monotonic()
    corpus_raw=a.corpus_manifest.read_bytes();corpus=json.loads(corpus_raw);corpus_sha=hashlib.sha256(corpus_raw).hexdigest()
    all_nodes=[];partition=[];provenance=dict(corpus_manifest=corpus_sha)
    for name,path in [('train',a.training),('validation',a.validation)]:
        manifest=json.loads(path.read_text());provenance[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest['partition']!=name or manifest['manifest_sha256']!=corpus_sha:raise ValueError('partition mismatch')
        for entry in manifest['cases']:
            if entry['status']!='complete':continue
            if entry['split']!=name:raise ValueError('case partition mismatch')
            raw=read_bytes(Path(entry['trace']))
            if hashlib.sha256(raw).hexdigest()!=entry['trace_sha256']:raise ValueError('trace hash mismatch')
            nodes=dataset(json.loads(raw),a.channels,a.zero_role_channels,a.encoding);offset=len(all_nodes)
            for n in nodes:n['edges']=[(i+offset,v) for i,v in n['edges']]
            all_nodes.extend(nodes);partition.extend([name]*len(nodes))
    raw=read_bytes(a.test_trace);test_trace=json.loads(raw)
    cases=[e for e in corpus['cases'] if e.get('program_sha256')==test_trace['program_sha256']]
    if len(cases)!=1 or cases[0]['split']!='test':raise ValueError('test partition mismatch')
    original=json.loads(read_bytes(Path(cases[0]['program'])))
    if original['recipe']!=test_trace['recipe']:raise ValueError('test recipe mismatch')
    test=dataset(test_trace,a.channels,a.zero_role_channels,a.encoding);provenance['test_trace']=hashlib.sha256(raw).hexdigest()
    seed,q,target=arrays(all_nodes);pool=pooling(all_nodes,target)
    raw_width=seed.shape[1]+q.shape[1]+256*a.channels
    rng=np.random.default_rng(412);w=rng.normal(0,1/np.sqrt(raw_width),(raw_width,256)).astype(np.float32)
    x=features(seed,q,pool,w,np);parts=np.array(partition);valid=np.array([n['valid'] for n in all_nodes])
    preparation_seconds=time.monotonic()-preparation_started
    fitting_started=time.monotonic()
    coef,fit=train(x,np.arctanh(np.clip(target,-.999,.999)),(parts=='train')&valid,(parts=='validation')&valid)
    zero_coef,zero_fit=train(features(seed,q,np.zeros_like(pool),w,np),np.arctanh(np.clip(target,-.999,.999)),
        (parts=='train')&valid,(parts=='validation')&valid)
    fitting_seconds=time.monotonic()-fitting_started
    with a.model.open('wb') as f:np.savez_compressed(f,w=w,coef=coef,zero_provider_coef=zero_coef,channels=a.channels,zero_role_channels=a.zero_role_channels,encoding=a.encoding)
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);seed,q,target=arrays(test);pool=pooling(test,target)
    oracle=mx.tanh(features(mx.array(seed),mx.array(q),mx.array(pool),mx.array(w),mx)@mx.array(coef));mx.eval(oracle)
    gold=np.tanh(features(seed,q,pool,w,np)@coef)
    no_provider=np.tanh(features(seed,q,np.zeros_like(pool),w,np)@zero_coef)
    shuffled=pooling(test,target[np.random.default_rng(991).permutation(len(test))])
    shuffled_pred=np.tanh(features(seed,q,shuffled,w,np)@coef)
    started=time.monotonic();pred=replay(test,w,coef,True);gpu_wall=time.monotonic()-started
    started=time.monotonic();cpu=replay(test,w,coef,False);cpu_wall=time.monotonic()-started
    valid=np.array([n['valid'] for n in test]);linked=np.array([n['linked'] for n in test]);multiple=np.array([n['multiple'] for n in test])
    audit=np.isfinite(pred).all() and np.isfinite(cpu).all();outside=int(np.count_nonzero(abs(pred-cpu)>.002+.004*abs(cpu)))
    oracle_outside=int(np.count_nonzero(abs(np.array(oracle)-gold)>.002+.004*abs(gold)))
    result=dict(scope='observed-wiring multi-provider numeric Cell token replay, not autonomous egraph execution',
        provenance=provenance,fit=fit,backpropagation=False,state_width=WIDTH,train_valid=int(sum(n['valid'] and p=='train' for n,p in zip(all_nodes,partition))),
        encoding=a.encoding,channels=a.channels,zero_role_channels=a.zero_role_channels,raw_feature_width=raw_width,
        edge_coefficient_floats=sum(v.size for n in test for _,v in n['edges']),
        route_coefficient_floats=sum(v.size for n in test for v in n['edge_routes']),
        expanded_edge_equivalent_floats=sum(v.size*a.channels for n in test for _,v in n['edges']),
        inference_weight_floats=int(w.size+coef.size),
        model_coefficient_floats=int(w.size+coef.size+zero_coef.size),
        preparation_seconds=preparation_seconds,fitting_seconds=fitting_seconds,
        consumed_cpu_boundary_tokens=len({i for n in test for i,_ in n['edges'] if not test[i]['valid']}),
        test_cases=len(test),cpu_boundary_tokens=int((~valid).sum()),depths=max(n['depth'] for n in test)+1,
        reports={label:dict(gold_provider_inputs=metric(np.array(oracle),target,m),predicted_provider_inputs=metric(pred,target,m),no_provider_refit=metric(no_provider,target,m),shuffled_providers=metric(shuffled_pred,target,m))
                 for label,m in [('all_valid',valid),('linked',valid&linked),('multiple_providers',valid&multiple)]},
        history_context=(('earliest' if a.encoding in ('class-history-earliest','class-history-neighborhood','class-history-neighborhood-input') else 'latest')+' observed constructor Run per typed identity; unproved lifetime') if a.encoding.startswith('class-history') else None,
        encoding_audit=dict(train_validation=encoding_audit(all_nodes),test=encoding_audit(test)),no_provider_fit=zero_fit,
        numerical_audit=dict(passed=bool(audit and outside==0 and oracle_outside==0),rollout_outside=outside,gold_outside=oracle_outside),
        gpu_replay_wall_seconds=gpu_wall,cpu_replay_wall_seconds=cpu_wall,
        intermediate_cpu_state_reads=0,model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),
        limitations=['Observed successful matches and routing are supplied by CPU traces',
            'Incomplete captured states are supplied as explicit CPU boundary tokens',
            'Dense code has no exact graph decoder, ownership certificate, novelty or saturation head',
            'External input observations supplied per consumer; their autonomous production is not tested',
            'Timing includes compilation and plan/upload work; no throughput or speedup claim'])
    a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not result['numerical_audit']['passed']:raise SystemExit(1)

if __name__=='__main__':main()
