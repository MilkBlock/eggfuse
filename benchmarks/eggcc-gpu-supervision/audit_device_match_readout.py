"""Frozen Eq readout on actual GPU joint-match samples and CPU-derived labels."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from token_eq_readout import pair_layout,static_equalities,quotient_layout,readout_rows,materialize
from audit_training_expansion import summarize


def rows_from_labels(recipe,rules,labels):
    if len(rules)!=len(labels):raise ValueError('label alignment')
    rows=[]
    for index,(rid,classes) in enumerate(zip(rules,labels)):
        rule=recipe['rules'][int(rid)];pairs,q,s,d,p=pair_layout(rule)
        if any(a>=len(classes) or b>=len(classes) or classes[a]<0 or classes[b]<0 for a,b in pairs):raise ValueError('missing CPU Eq label')
        y=np.array([classes[a]==classes[b] for a,b in pairs],bool);static=static_equalities(rule,pairs)
        if (static&~y).any():raise ValueError('CPU label contradicts static equality')
        rows.append(dict(index=index,pairs=pairs,q=q,s=s,d=d,p=p,y=y,static=static,quotient=quotient_layout(rule,pairs,static)))
    return rows



def dynamic_metrics(truth,scores):
    truth=np.asarray(truth,bool);scores=np.asarray(scores).reshape(-1)
    if truth.shape!=scores.shape or not np.isfinite(scores).all():raise ValueError('dynamic score alignment')
    predicted=scores>=.5;tp=int(np.count_nonzero(predicted&truth));fp=int(np.count_nonzero(predicted&~truth));fn=int(np.count_nonzero(~predicted&truth))
    return dict(queries=len(truth),positives=int(truth.sum()),true_positives=tp,false_positives=fp,false_negatives=fn,
        precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None)


def main():
    p=argparse.ArgumentParser()
    for key in ('capture','decoder','decoder_report','output'):p.add_argument(key,type=Path)
    a=p.parse_args();started=time.monotonic();meta=json.loads(a.capture.with_suffix('.json').read_text());report=json.loads(a.decoder_report.read_text())
    if hashlib.sha256(a.capture.read_bytes()).hexdigest()!=meta['capture']['artifact_sha256']:raise ValueError('capture hash')
    if meta['capture']['schema'] not in ('device-joint-witness/v2','device-joint-witness/v3') or not meta['capture']['passed']:raise ValueError('unverified target capture')
    if meta['capture']['schema']=='device-joint-witness/v3' and 'semantic_recipe' not in meta:raise ValueError('semantic target definition missing')
    if hashlib.sha256(a.decoder.read_bytes()).hexdigest()!=report['weights_sha256']:raise ValueError('decoder hash')
    if meta['model_sha256']!=report['model_sha256']:raise ValueError('decoder parent model mismatch')
    if meta.get('completion_readout') and meta['completion_readout']['decoder_sha256']!=report['weights_sha256']:raise ValueError('completion decoder mismatch')
    with np.load(a.capture) as data:
        ids=[meta['source_rules'].index(int(r)) for r in data['rules']]
        rows=rows_from_labels(meta.get('semantic_recipe',meta['recipe']),ids,data['target_eq_classes'])
        targets=data['targets'];predicted=data['predicted_tokens']
        sample_rules=data['rules'].copy();generated=data['generated_source'].copy() if 'generated_source' in data else None
        label_stats=dict(full_pair_queries=sum(len(r['pairs']) for r in rows),static_equalities=sum(int(r['static'].sum()) for r in rows),
            dynamic_quotient_queries=sum(len(r['quotient']['representatives']) for r in rows),dynamic_true_equalities=sum(int(r['y'][r['quotient']['representatives']].sum()) for r in rows),
            distinct_rule_partitions=len({(int(rid),tuple(classes)) for rid,classes in zip(data['rules'],data['target_eq_classes'])}))
    if len(rows)!=meta['capture']['samples'] or len(targets)!=len(rows) or len(predicted)!=len(rows):raise ValueError('sample alignment')
    with np.load(a.decoder) as data:weights={k:data[k] for k in data.files}
    index=np.flatnonzero(weights['alphas']==report['selected']['partition'])
    if len(index)!=1:raise ValueError('decoder selection')
    coef=weights['coef'][:,index];result={}
    for name,tokens in [('cpu_target_token',targets),('gpu_predicted_token',predicted)]:
        features,truth=materialize(readout_rows(rows,True),tokens,weights['w'],True)
        scores=(features@coef).reshape(-1)
        result[name]=dict(summarize(rows,scores),dynamic_quotient=dynamic_metrics(truth,scores))
    selected_state_audit=None
    if meta.get('completion_readout'):
        from audit_input_relations import restore
        chosen=[];locations=[]
        with np.load(a.capture) as data:
            prefixes=[k[:-4] for k in data.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k]
            prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
            for prefix in prefixes:
                c=restore(data,prefix)
                if bool(c['recorded']):
                    chosen.extend(c['completion_readout']['selected'][c['accepted']])
                    for lane in np.flatnonzero(c['accepted']):
                        locations.append(dict(capture_prefix=prefix,lane=int(lane),rule=int(meta['source_rules'][int(c['rule'])]),
                            witness_rows=c['bindings']['witness_rows'][lane].tolist(),
                            witness_generations=c['bindings']['witness_generations'][lane].tolist()))
        if len(chosen)!=len(rows):raise ValueError('selected completion state alignment')
        flat=np.concatenate(chosen)
        if len(flat)!=len(scores):raise ValueError('selected completion pair layout')
        rejected=[]
        for i,(row,value) in enumerate(zip(rows,chosen)):
            ids=row['quotient']['representatives'];wanted=row['y'][ids];actual=value>=.5
            if np.array_equal(wanted,actual):continue
            pairs=[row['pairs'][j] for j in ids]
            rejected.append(dict(locations[i],sample=i,generated_source=bool(generated[i]) if generated is not None else None,
                false_quotient_pairs=[list(pair) for pair,yes in zip(pairs,actual&~wanted) if yes],
                missed_quotient_pairs=[list(pair) for pair,yes in zip(pairs,~actual&wanted) if yes]))
        selected_state_audit=dict(summarize(rows,flat),dynamic_quotient=dynamic_metrics(truth,flat),
            decoded_token_disagreements=int(np.count_nonzero((scores>=.5)!=(flat>=.5))),
            rejected_instances=len(rejected),rejected_fraction=len(rejected)/len(rows),local_diagnostics=rejected,
            diagnostic_scope='post-execution CPU label rejection at captured inputs; not a repair ticket or an applied correction')
    groups={}
    selectors={('rule_'+str(int(r))):sample_rules==r for r in np.unique(sample_rules)}
    if generated is not None:selectors.update(direct_source=~generated,generated_source=generated)
    for group,mask in selectors.items():
        selected=[r for r,m in zip(rows,mask) if m]
        if not selected:continue
        groups[group]={}
        for name,tokens in [('cpu_target_token',targets),('gpu_predicted_token',predicted)]:
            x,truth=materialize(readout_rows(selected,True),tokens,weights['w'],True)
            scores=(x@coef).reshape(-1)
            groups[group][name]=dict(summarize(selected,scores),dynamic_quotient=dynamic_metrics(truth,scores))
    out=dict(scope='actual selected-family GPU token Eq readout; no fitting or union authorization',case=meta['capture']['case'],partition=meta['capture']['partition'],
        source_token_mode=meta.get('source_token_mode','exact completed states'),completion_readout=meta.get('completion_readout'),
        selected_state_audit=selected_state_audit,
        capture_sha256=meta['capture']['artifact_sha256'],adapter_sha256=meta.get('adapter_sha256'),inference_coefficients_sha256=meta.get('inference_coefficients_sha256'),decoder_sha256=report['weights_sha256'],label_statistics=label_stats,static_only_baseline=summarize(rows,np.zeros(label_stats['dynamic_quotient_queries'],np.float32)),results=result,groups=groups,
        cpu_readout_audit_seconds=time.monotonic()-started,backpropagation=False,union_authorized=False,
        limitations=['Small selected immutable Cell family, not full Eggcc','Exact execution establishes completion; ridge is audited separately','Test samples must not be used for fitting'])
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
