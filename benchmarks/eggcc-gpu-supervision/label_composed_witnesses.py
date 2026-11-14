"""CPU-derived saturated labels for actual generated-source GPU witnesses.

All target construction is post-execution. Future partitions never enter inputs.
"""
import argparse,hashlib,json,time
from copy import deepcopy
from pathlib import Path
import numpy as np
from audit_input_relations import restore
from device_match_capture import audit,floating_inputs,partition
from device_input_relations import inputs,encode as relation_features,projection
from device_snapshot_import import prepare_family
from lower_constructor_sets import lower
from reference_union_family import Reference
from reference_cell_closure import facts_from_cells
from multi_entry_ridge import template,encode
from device_semantic_template import semantic
from audit_device_match_readout import rows_from_labels


def source_facts(capture,recipe):
    w=capture['witness'];live=capture['bindings']['live']
    # Witness fields already project the actual owner payload. No second match.
    slots=w['slots'][live].reshape(-1,w['slots'].shape[-1]);n=len(slots)
    state={k:w[k][live].reshape(-1) for k in ('present','visible','settled','effect_pc')}
    state.update(slots=slots,slot_valid=w['slot_valid'][live].reshape(slots.shape),keys=w['rule'][live].reshape(n,1))
    facts,covered=facts_from_cells(recipe,state)
    if not covered:raise ValueError('source facts incomplete')
    return facts


def resolve_identities(reference,facts,seed_count):
    """Map stable GPU addresses to independently computed CPU classes.

    This map is for labels only. Distinct stable addresses may share a final
    class; current input Eq is never inferred from this future mapping.
    """
    mapping={i:reference.root(i) for i in range(seed_count)}
    expected={(t,v[:-1]):v[-1] for t,v in reference.normalized_facts()}
    pending=list(set(facts))
    for _ in range(len(pending)+1):
        todo=[];progress=False
        for table,args,result in pending:
            if any(a not in mapping for a in args):todo.append((table,args,result));continue
            key=(table,tuple(mapping[a] for a in args))
            if key not in expected:raise ValueError('source constructor absent from CPU saturation')
            wanted=expected[key]
            if result in mapping and mapping[result]!=wanted:raise ValueError('source identity contradicts CPU')
            progress |= result not in mapping;mapping[result]=wanted
        pending=todo
        if not pending:return mapping
        if not progress:break
    raise ValueError('unresolved source identities')


def target(rule,binding,mapping,reference,seed_values,width):
    values={i:mapping[int(binding[i])] for i,s in enumerate(rule['slots']) if s['definition']=='query'}
    facts={(t,v[:-1]):v[-1] for t,v in reference.normalized_facts()}
    for op in rule['effects']:
        if op['kind']=='copy':values[op['dst']]=values[op['arg']['slot']]
        elif op['kind']=='construct':
            key=(op['call']['table'],tuple(values[a['slot']] for a in op['args']))
            if key not in facts:raise ValueError('CPU completion constructor missing')
            values[op['dst']]=facts[key]
        elif op['kind']=='union':
            if values[op['args'][0]['slot']]!=values[op['args'][1]['slot']]:raise ValueError('CPU union target disagrees')
        else:raise ValueError('unsupported target effect')
    if set(values)!=set(range(len(rule['slots']))):raise ValueError('incomplete target slots')
    semantic_rule,_=semantic(rule)
    encoded=[];labels=np.full(width,-1,np.int32);classes={}
    for slot,value in sorted(values.items()):
        if slot>=len(semantic_rule['slots']):continue
        sort=semantic_rule['slots'][slot]['sort']
        if sort['kind']=='eq':
            key=(sort['name'],value);encoded.append((slot,{},key));labels[slot]=classes.setdefault(key,len(classes))
        else:
            if value not in seed_values or seed_values[value]['sort']!=sort['name'] or 'eq' in seed_values[value]:raise ValueError('unsupported scalar result')
            encoded.append((slot,seed_values[value],None))
    return encode(encoded,template(semantic_rule)[0],'class-balanced'),labels


def main():
    p=argparse.ArgumentParser()
    for k in ('capture','trace','model','corpus','output','report'):p.add_argument(k,type=Path)
    p.add_argument('--semantic-targets',action='store_true',help='project legacy captures onto original Cell semantics for a like-for-like audit')
    p.add_argument('--snapshot-run',type=int,required=True);a=p.parse_args();start=time.monotonic()
    meta=json.loads(a.capture.with_suffix('.json').read_text());trace=json.loads(a.trace.read_bytes())
    if meta['capture']['schema']!='device-composed-witness/v1' or not meta['capture']['passed'] or hashlib.sha256(a.capture.read_bytes()).hexdigest()!=meta['capture']['artifact_sha256']:raise ValueError('capture provenance')
    if hashlib.sha256(a.trace.read_bytes()).hexdigest()!=meta['trace_sha256'] or hashlib.sha256(a.model.read_bytes()).hexdigest()!=meta['model_sha256']:raise ValueError('source provenance')
    provenance=partition(trace,a.corpus);original=dict(trace['recipe'],rules=[trace['recipe']['rules'][i] for i in meta['source_rules']])
    if original!=meta['original_recipe']:raise ValueError('original rule definitions')
    lowered,_=lower(original);snapshots=[b['graph'] for b in trace['boundaries'] if b['ordinal']==a.snapshot_run]
    if len(snapshots)!=1:raise ValueError('snapshot ordinal')
    local,state,ids,rows=prepare_family(lowered,snapshots[0],list(range(len(original['rules']))),1)
    target_recipe=deepcopy(local)
    if not any('token_layout' in r for r in meta['recipe']['rules']):
        for r in local['rules']:r.pop('token_layout',None)
    if local!=meta['recipe']:raise ValueError('lowered recipe')
    if not a.semantic_targets:target_recipe=local
    semantic_recipe=dict(local,rules=[semantic(r)[0] for r in target_recipe['rules']])
    ref=Reference(original,rows,ids);runs=ref.saturate(original['rules'])
    with np.load(a.model) as f:model={k:f[k] for k in ('w','coef')}
    captures=[];facts=[];saved={}
    with np.load(a.capture) as data:
        prefixes=[k[:-4] for k in data.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k]
        prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
        for prefix in prefixes:
            c=restore(data,prefix)
            if not bool(c['recorded']):continue
            checked=audit(local,c)
            if not checked['passed'] or not checked['enumeration_complete']:raise ValueError('invalid selected witness')
            captures.append(c);facts.extend(source_facts(c,local))
        saved={k:data[k] for k in data.files}
    mapping=resolve_identities(ref,facts,len(ids));seed_values={i:json.loads(v) for v,i in ids.items()}
    boundary_features=[];boundary_error=0.;xs=[];extra=[];ys=[];labels=[];pred=[];rules=[];continued=[];numerical=0.
    for c in captures:
        x=floating_inputs(c,model,np);z,_=relation_features(inputs(local,c),projection(),np);rid=int(c['rule']);rule=local['rules'][rid]
        if 'boundary' in c:
            from device_boundary_context import compile_context,encode as boundary_encode
            bp=compile_context(local,rid,state['slots'].shape[1])
            bf,bc=boundary_encode(c['boundary'],c['bindings'],bp,np)
            boundary_error=max(boundary_error,float(np.max(abs(bf-c['boundary_features']))))
            if boundary_error>5e-6 or not np.array_equal(bc,c['boundary_counts']):raise ValueError('boundary feature mismatch')
            boundary_features.extend(c['boundary_features'][c['accepted']])
        live=c['bindings']['live']
        if live.any():numerical=max(numerical,float(np.max(abs(np.tanh(x@model['coef'])[live]-c['predicted_tokens'][live]))))
        for lane in np.flatnonzero(c['accepted']):
            y,label=target(target_recipe['rules'][rid],c['bindings']['slots'][lane],mapping,ref,seed_values,state['slots'].shape[1])
            xs.append(x[lane]);extra.append(z[lane]);ys.append(y);labels.append(label);pred.append(c['predicted_tokens'][lane]);rules.append(meta['source_rules'][rid])
            continued.append(bool(np.any(c['request']['edge_valid'][lane]&(c['source_rules'][lane]<len(original['rules'])))))
    if numerical>5e-6:raise ValueError('floating inputs changed')
    rr=rows_from_labels(semantic_recipe,[meta['source_rules'].index(r) for r in rules],labels)
    payload=dict(features=np.array(xs,np.float32),input_relations=np.array(extra,np.float32),targets=np.array(ys,np.float32),target_eq_classes=np.array(labels,np.int32),predicted_tokens=np.array(pred,np.float32),rules=np.array(rules,np.int32),generated_source=np.array(continued,bool),**saved)
    if boundary_features:
        if len(boundary_features)!=len(xs):raise ValueError('partial boundary capture')
        payload['boundary_features']=np.array(boundary_features,np.float32)
    np.savez_compressed(a.output,**payload)
    result=dict(schema='device-joint-witness/v3' if a.semantic_targets or any('token_layout' in r for r in local['rules']) else 'device-joint-witness/v2',**provenance,passed=True,samples=len(xs),continued_samples=sum(continued),
        distinct_inputs=len(np.unique(payload['features'],axis=0)),distinct_targets=len(np.unique(payload['targets'],axis=0)),
        dynamic_eq_queries=sum(len(r['quotient']['representatives']) for r in rr),dynamic_eq_positive=sum(int(r['y'][r['quotient']['representatives']].sum()) for r in rr),
        artifact_sha256=hashlib.sha256(a.output.read_bytes()).hexdigest(),source_capture_sha256=meta['capture']['artifact_sha256'],
        boundary_feature_columns=payload['boundary_features'].shape[1] if boundary_features else 0,boundary_feature_max_abs=boundary_error,
        feature_reconstruction_max_abs=numerical,cpu_label_and_capture_audit_seconds=time.monotonic()-start,
        target_scope='original-rule CPU selected-family saturation; labels cover semantic Cell slots; compiler temporaries excluded where declared',backpropagation=False,
        limitations=['Labels are final family states, not every intermediate state','Selected context rules, not full Eggcc','Source tokens come from exact completed GPU states; recursive predicted-source rollout not established'])
    a.output.with_suffix('.json').write_text(json.dumps(dict(meta,semantic_recipe=semantic_recipe,snapshot_run=a.snapshot_run,seed_scalars={str(i):v for i,v in seed_values.items() if 'eq' not in v},capture=result),indent=2)+'\n')
    a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
