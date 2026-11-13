"""Exact f32 boundary-feature ambiguity audit, with no new fit or decoder choice."""
import argparse
from collections import defaultdict
import hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from audit_training_expansion import verified
from collect_observed_corpus import read_bytes
from token_eq_readout import examples,readout_rows,materialize
from packed_cell_replay import executor,prepare,audit
from multi_entry_ridge import arrays,features,WIDTH,input_rows,state_key


def ambiguity(matrix,labels,scopes,locations):
    matrix=np.asarray(matrix,np.float32).copy()
    if not np.isfinite(matrix).all():raise ValueError('nonfinite features')
    matrix[matrix==0]=0  # Normalize signed zero; numeric equality is what matters.
    if not(len(matrix)==len(labels)==len(scopes)==len(locations)):raise ValueError('row alignment')
    groups={}
    for feature,label,scope,location in zip(matrix,labels,scopes,locations):
        key=(scope,feature.tobytes());group=groups.setdefault(key,dict(counts=[0,0],examples=[None,None]))
        i=int(label);group['counts'][i]+=1
        if group['examples'][i] is None:group['examples'][i]=location
    conflicts=[g for g in groups.values() if all(g['counts'])]
    return dict(queries=len(labels),positive_queries=int(np.sum(labels)),distinct_features=len(groups),
        conflicting_features=len(conflicts),queries_in_conflicts=sum(sum(g['counts']) for g in conflicts),
        unavoidable_query_errors=sum(min(g['counts']) for g in conflicts),
        witnesses=[dict(negative=g['examples'][0],positive=g['examples'][1],counts=g['counts']) for g in conflicts[:8]])


def model_inputs(nodes,states,w,plan):
    """Diagnostic reconstruction with the replay plan's fixed GPU aggregation shapes."""
    seed,q,_=arrays(nodes);seed,q,state,weight=map(mx.array,(seed,q,states,w))
    channels=nodes[0]['edge_width']//WIDTH;result=np.zeros((len(nodes),1+w.shape[0]+w.shape[1]),np.float32)
    for layer in plan:
        chunks=[]
        for group in layer['groups']:
            if group['sources'].shape[1]==0:chunks.append(mx.zeros((group['rows'],channels*WIDTH)))
            else:
                route=mx.array(group['route']);base=mx.array(group['base']);sources=mx.array(group['sources'])
                chunks.append(mx.matmul(mx.swapaxes(route,1,2),state[sources]*base).reshape(group['rows'],channels*WIDTH))
        ids=mx.array(layer['ids']);out=features(seed[ids],q[ids],mx.concatenate(chunks,axis=0),weight,mx)
        mx.eval(out);result[layer['ids']]=np.array(out)
    return result


def trace_witnesses(trace,nodes,rows,predicted,model,witnesses):
    if not witnesses:return dict(witnesses=[])
    plan=prepare(nodes,'two');inputs=model_inputs(nodes,predicted,model['w'],plan)
    oracle_inputs=model_inputs(nodes,np.array([n['target'] for n in nodes]),model['w'],plan)
    valid=np.array([n['valid'] for n in nodes]);recomputed=np.tanh(inputs@model['coef'])
    numeric=audit(recomputed[valid],predicted[valid])
    if not numeric['passed']:raise ValueError('model input reconstruction mismatch')
    address={(r['run'],r['ordinal']):r['index'] for r in rows}
    bindings={(run['ordinal'],i):b for run in trace['runs'] for i,b in enumerate(run['audit']['bindings'])}
    out=[]
    for witness in witnesses:
        a,b=[address[(witness[k]['run'],witness[k]['binding'])] for k in ('negative','positive')]
        detail=dict(witness,identical_predicted_tokens=bool(np.array_equal(predicted[a],predicted[b])),
            identical_reconstructed_inputs=bool(np.array_equal(inputs[a],inputs[b])),
            identical_oracle_provider_inputs=bool(np.array_equal(oracle_inputs[a],oracle_inputs[b])),
            input_max_abs_difference=float(np.max(abs(inputs[a]-inputs[b]))),
            oracle_input_max_abs_difference=float(np.max(abs(oracle_inputs[a]-oracle_inputs[b]))),
            provider_edges=[len(nodes[i]['edges']) for i in (a,b)])
        for name in ('negative','positive'):
            location=witness[name];binding=bindings[(location['run'],location['binding'])]
            ports={s['slot']:s['eq_port'] for s in binding['rhs']['slots'] if 'eq_port' in s}
            x,y=[ports[i] for i in location['slots']]
            detail[name+'_at_rhs_equal']=x['sort']==y['sort'] and x['at_rhs']==y['at_rhs']
            detail[name+'_after_run_equal']=x['sort']==y['sort'] and x['after_run']==y['after_run']
        pair_bindings=[bindings[(witness[k]['run'],witness[k]['binding'])] for k in ('negative','positive')]
        detail['identical_normalized_input_bindings']=state_key(input_rows(pair_bindings[0]))==state_key(input_rows(pair_bindings[1]))
        detail['rule_name']=trace['recipe']['rules'][witness['positive']['rule']]['metadata']['name']
        out.append(detail)
    return dict(witnesses=out,reconstruction_numeric_audit=numeric,
        scope='bounded collision witnesses; reconstructed GPU aggregation, not an instrumented intermediate execution trace')


def main():
    p=argparse.ArgumentParser();p.add_argument('training',type=Path);p.add_argument('validation',type=Path)
    p.add_argument('test',type=Path);p.add_argument('model',type=Path);p.add_argument('model_report',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    report=json.loads(a.model_report.read_text());model=verified(a.model,report,'model_sha256')
    config=(int(model['channels']),bool(model['zero_role_channels']),str(model.get('encoding','slot')))
    cases=[];provenance={}
    for split,path in [('train',a.training),('validation',a.validation)]:
        raw=path.read_bytes();manifest=json.loads(raw);provenance[split]=hashlib.sha256(raw).hexdigest()
        if manifest['partition']!=split or manifest['manifest_sha256']!=report['provenance']['corpus_manifest']:raise ValueError('partition mismatch')
        if split=='train' and provenance[split]!=report['provenance']['train']:raise ValueError('training mismatch')
        for entry in manifest['cases']:
            if entry['status']=='complete':
                if entry['split']!=split:raise ValueError('case partition mismatch')
                cases.append((split,entry['case'],Path(entry['trace']),entry['trace_sha256']))
    cases.append(('test','dot-product',a.test,report['provenance']['test_trace']))
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu)
    w=np.random.default_rng(208).normal(0,1/np.sqrt(512),(512,256)).astype(np.float32)
    results=[];started=time.monotonic()
    for split,case,path,expected in cases:
        raw=read_bytes(path)
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('trace mismatch')
        trace=json.loads(raw);nodes,rows=examples(trace,config[0],config[1],True,config[2]);query=readout_rows(rows,True)
        predicted=np.array(executor(nodes,model['w'],model['coef'],prepare(nodes,'two'),True)())
        scopes=[];locations=[]
        for r in query:
            for pair in r['pairs']:
                scopes.append(r['node']['family'])
                locations.append(dict(run=r['run'],binding=r['ordinal'],rule=r['rule'],slots=list(pair)))
        entry=dict(split=split,case=case,trace_sha256=expected,complete_instances=len(rows),incomplete_instances=len(nodes)-len(rows),modes={})
        for mode,tokens in [('oracle',np.array([n['target'] for n in nodes])),('predicted',predicted)]:
            matrix,y=materialize(query,tokens,w,True)
            entry['modes'][mode]=ambiguity(matrix,y,scopes,locations)
        entry['attribution']=trace_witnesses(trace,nodes,rows,predicted,model,entry['modes']['predicted']['witnesses'])
        results.append(entry);print(json.dumps(dict(case=case,modes={k:{f:v[f] for f in ('queries','conflicting_features','unavoidable_query_errors')} for k,v in entry['modes'].items()})),flush=True)
    aggregate={}
    for split in ('train','validation','test'):
        aggregate[split]={mode:{field:sum(r['modes'][mode][field] for r in results if r['split']==split)
            for field in ('queries','positive_queries','distinct_features','conflicting_features','queries_in_conflicts','unavoidable_query_errors')} for mode in ('oracle','predicted')}
    out=dict(scope='within-case, within-template exact f32 decoder-feature ambiguity audit',model_sha256=report['model_sha256'],
        provenance=provenance,encoding=config[2],cases=results,aggregate=aggregate,wall_seconds=time.monotonic()-started,
        fitting=False,union_authorized=False,limitations=['No conflicts does not establish separability, robustness or decoder adequacy',
            'Lower bounds count class queries, not expanded slot pairs or full partitions',
            'Aggregation sums per-case audits and does not discover cross-case collisions',
            'Actual CPU matches/routes and external observations still supplied to GPU replay',
            'Only exact f32 feature equality is tested; near-collisions and hidden lifecycle facts remain untested'])
    a.output.write_text(json.dumps(out,indent=2)+'\n')

if __name__=='__main__':main()
