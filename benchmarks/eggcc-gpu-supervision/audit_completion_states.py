"""Project frozen readout onto all static-compatible local Eq partitions.

Diagnostic only: no training, no model adoption, no learned union authorization.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import mlx.core as mx
from calibrate_semantic_family import load
from device_completion_states import compile_states, compile_tokens, tokens as make_tokens, project
from audit_input_relations import restore
from multi_entry_ridge import scalar
from token_eq_readout import materialize, readout_rows
from audit_training_expansion import summarize
from audit_device_match_readout import dynamic_metrics


def captured_inputs(path, meta):
    values=[]
    with np.load(path) as f:
        prefixes=[k[:-4] for k in f.files if k.startswith('capture/') and k.endswith('/rule')
                  and '/witness/' not in k and '/boundary/' not in k]
        prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
        for prefix in prefixes:
            c=restore(f,prefix)
            if not bool(c['recorded']):continue
            for lane in np.flatnonzero(c['accepted']):
                values.append((int(meta['source_rules'][int(c['rule'])]), {k:c['bindings'][k][lane] for k in ('slots','slot_roots','slot_valid')}))
    return values


def main():
    p=argparse.ArgumentParser()
    for key in ('decoder','decoder_report','output'):p.add_argument(key,type=Path)
    p.add_argument('--capture',type=Path,action='append',required=True)
    a=p.parse_args();dr=json.loads(a.decoder_report.read_text())
    sha=hashlib.sha256(a.decoder.read_bytes()).hexdigest()
    if sha!=dr['weights_sha256']:raise ValueError('decoder hash')
    with np.load(a.decoder) as f:
        w=f['w'];selected=np.flatnonzero(f['alphas']==dr['selected']['partition'])
        if len(selected)!=1:raise ValueError('decoder selection')
        coef=f['coef'][:,selected]
    cases=[];max_error=0.;max_token_error=0.;max_target_error=0.
    mx.set_default_device(mx.gpu)
    for path in a.capture:
        d,m=load(path,'validation')
        if m['model_sha256']!=dr['model_sha256']:raise ValueError('decoder model identity')
        with np.load(path) as f:tokens=f['predicted_tokens']
        rows=d['rows'];query=readout_rows(rows,True)
        current=captured_inputs(path,m)
        if len(current)!=len(rows) or any(r!=int(want) for (r,_),want in zip(current,d['rules'])):raise ValueError('current input alignment')
        x,truth=materialize(query,tokens,w,True);scores=(x@coef).ravel()
        if not np.isfinite(scores).all():raise ValueError('nonfinite scores')
        cuts=np.cumsum([0]+[len(r['y']) for r in query])
        projected=scores.copy();constrained=scores.copy();plans={};complete=0;input_equalities=0
        for rid in np.unique(d['rules']):
            semantic_id=m['source_rules'].index(int(rid))
            rule=m['semantic_recipe']['rules'][semantic_id]
            plan=compile_states(rule);states=plan['states'];token_plan=compile_tokens(rule,plan)
            ids=np.flatnonzero(d['rules']==rid)
            batched=np.stack([scores[cuts[i]:cuts[i+1]] for i in ids])
            labels=np.stack([query[i]['y'] for i in ids])
            # Labels are checked ONLY after template enumeration; not used in projection.
            represented=np.any(np.all(labels[:,None,:]==states[None,:,:],axis=-1),axis=1)
            if not represented.all():raise ValueError('target not represented by static state family')
            complete+=int(represented.sum())
            required=np.zeros_like(batched,bool)
            result,index=project(batched,states,required,np)
            device=mx.compile(lambda v,r:project(v,mx.array(states),r,mx))
            actual,actual_index=device(mx.array(batched),mx.array(required));mx.eval(actual,actual_index)
            error=float(np.max(abs(np.array(actual)-result),initial=0));max_error=max(max_error,error)
            if error or not np.array_equal(actual_index,index):raise ValueError('GPU state selection differs')
            for i,value in zip(ids,result):projected[cuts[i]:cuts[i+1]]=value
            scalar_codes=[]
            for lane,i in enumerate(ids):
                binding=current[i][1]
                for (aa,bb),q in zip(plan['pairs'],plan['quotient']['expansion']):
                    if q>=0 and all(rule['slots'][s]['definition']=='query' and binding['slot_valid'][s] for s in (aa,bb)):
                        if binding['slot_roots'][aa]<0 or binding['slot_roots'][bb]<0:raise ValueError('invalid current Eq root')
                        required[lane,q] |= binding['slot_roots'][aa]==binding['slot_roots'][bb]
                codes=[]
                for s in token_plan['scalar_slots']:
                    if rule['slots'][s]['definition']!='query' or not binding['slot_valid'][s]:raise ValueError('scalar result needs an actual execution source')
                    value=m['seed_scalars'][str(int(binding['slots'][s]))]
                    if value['sort']!=rule['slots'][s]['sort']['name']:raise ValueError('scalar type mismatch')
                    codes.append(scalar(value))
                scalar_codes.append(codes)
            codes=np.array(scalar_codes,np.float32).reshape(len(ids),len(token_plan['scalar_slots']),64)
            input_equalities+=int(required.sum())
            if np.any(required & ~labels):raise ValueError('current Eq contradicts completion labels')
            result,index=project(batched,states,required,np)
            out,device_index=device(mx.array(batched),mx.array(required));mx.eval(out,device_index)
            np.testing.assert_array_equal(out,result);np.testing.assert_array_equal(device_index,index)
            for i,value in zip(ids,result):constrained[cuts[i]:cuts[i+1]]=value
            encoded=make_tokens(index,codes,token_plan,np)
            device_plan={k:mx.array(v) for k,v in token_plan.items()}
            rebuilt=mx.compile(lambda ix,sc:make_tokens(ix,sc,device_plan,mx))(device_index,mx.array(codes));mx.eval(rebuilt)
            max_token_error=max(max_token_error,float(np.max(abs(np.array(rebuilt)-encoded))))
            # Oracle state only validates representation; never used in predictions.
            oracle=np.argmax(np.all(labels[:,None,:]==states[None,:,:],axis=-1),axis=1)
            oracle_tokens=make_tokens(oracle,codes,token_plan,np)
            max_target_error=max(max_target_error,float(np.max(abs(oracle_tokens-d['targets'][ids]))))
            plans[str(int(rid))]=dict(states=len(states),quotient_pairs=states.shape[1],matrix_bytes=states.nbytes,
                token_moment_bytes=sum(token_plan[k].nbytes for k in ('first','second','counts','scalar_roles')))
        groups={}
        for name,mask in dict(all=np.ones(len(rows),bool),direct=~d['generated_source'],generated=d['generated_source']).items():
            selected=[r for r,yes in zip(rows,mask) if yes]
            flat=np.concatenate([np.arange(cuts[i],cuts[i+1]) for i in np.flatnonzero(mask)]) if mask.any() else np.array([],int)
            groups[name]={kind:dict(summarize(selected,value[flat]),dynamic_quotient=dynamic_metrics(truth[flat],value[flat]))
                          for kind,value in [('independent',scores),('whole_state',projected),('current_input_state',constrained)]}
        cases.append(dict(case=m['capture']['case'],capture_sha256=m['capture']['artifact_sha256'],
            source_token_mode=m.get('source_token_mode','exact completed states'),plans=plans,
            targets_represented=complete,current_input_equalities=input_equalities,groups=groups))
    if max_token_error>5e-6 or max_target_error>5e-6:raise ValueError('full token representation mismatch')
    out=dict(scope='frozen Eq-readout projection diagnostic on actual GPU captures',backpropagation=False,
        refitting=False,installed=False,union_authorized=False,decoder_sha256=sha,maximum_gpu_selection_error=max_error,
        maximum_gpu_token_error=max_token_error,maximum_oracle_token_error=max_target_error,cases=cases,
        limitations=['Local type-compatible states are not proven reachable completions',
            'Enumeration is exponential and capped at 4096 states per Cell',
            'Current-input variant also enforces captured proven input Eq; no future equality is injected',
            'Full floating tokens are synthesized using actual query scalar values; new scalar effects need actual execution',
            'Stable IDs and ownership remain in existing runtime; reconstructed predictions have not undergone feedback rollout',
            'No CPU validation label participates in state compilation or selection',
            'Validation cases are development data, not final held-out acceptance'])
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
