"""Label-independent nearest-input audit for direct-source prediction failures.

Distances select neighbors without labels. Labels only describe their support.
This is not a nearest-neighbor inference path or a new trained predictor.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from calibrate_semantic_family import load,align_features,semantic_family
from token_eq_readout import readout_rows,materialize
from audit_training_expansion import summarize


def main():
    p=argparse.ArgumentParser()
    for k in ('model','decoder','decoder_report','output'):p.add_argument(k,type=Path)
    p.add_argument('--source-model',type=Path,action='append',default=[]);p.add_argument('--train',type=Path,action='append',required=True);p.add_argument('--validation',type=Path,action='append',required=True);a=p.parse_args()
    with np.load(a.model) as f:model={k:f[k] for k in f.files}
    dr=json.loads(a.decoder_report.read_text())
    model_sha=hashlib.sha256(a.model.read_bytes()).hexdigest()
    if dr['model_sha256']!=model_sha or hashlib.sha256(a.decoder.read_bytes()).hexdigest()!=dr['weights_sha256']:raise ValueError('frozen decoder provenance')
    with np.load(a.decoder) as f:
        chosen=np.flatnonzero(f['alphas']==dr['selected']['partition'])
        if len(chosen)!=1:raise ValueError('decoder selection')
        dw=f['w'];dc=f['coef'][:,chosen]
    allowed={model_sha}
    for path in a.source_model:
        with np.load(path) as f:
            for k in ('w','encoding','channels','zero_role_channels'):
                if not np.array_equal(f[k],model[k]):raise ValueError('incompatible source feature basis')
        allowed.add(hashlib.sha256(path.read_bytes()).hexdigest())
    training=[];validation=[];seen=set();family=None
    for split,paths in [('train',a.train),('validation',a.validation)]:
        for path in paths:
            d,m=load(path,split)
            if m['model_sha256'] not in allowed:raise ValueError('source model provenance')
            if m.get('source_token_mode','exact completed states')!='exact completed states':raise ValueError('requires exact-source inputs')
            sha=m['capture']['program_file_sha256']
            if sha in seen:raise ValueError('duplicate or leaked program')
            seen.add(sha);sf=semantic_family(m)
            if family is not None and sf!=family:raise ValueError('semantic family mismatch')
            family=sf;d['features'],_=align_features(d,model,True)
            records=[]
            for i,r in enumerate(d['rules']):
                # Full features have already been verified by capture labeling.
                records.append(dict(case=m['capture']['case'],sample=i,rule=int(r),x=d['features'][i],
                    y=d['rows'][i]['y'],row=d['rows'][i],generated=bool(d['generated_source'][i]),sha256=m['capture']['artifact_sha256']))
            (training if split=='train' else validation).extend(records)
    raw_width=model['w'].shape[0]
    if raw_width!=1408:raise ValueError('unsupported feature block layout')
    base_width=1+raw_width+model['w'].shape[1]
    blocks={'full':slice(None),'seed_and_query':slice(1,385),'source_pool_and_interaction':slice(385,1+raw_width),'boundary':slice(base_width,None)}
    results=[];failed=0;nearest_same=0;matching_target_present=0
    for r in validation:
        if r['generated']:continue
        row=dict(r['row'],index=0)
        token=np.tanh(r['x'][None]@model['coef'])
        xx,_=materialize(readout_rows([row],True),token,dw,True);scores=(xx@dc).ravel()
        metrics=summarize([row],scores)
        if metrics['exact_partitions']:continue
        failed+=1;candidates=[t for t in training if t['rule']==r['rule']]
        if not candidates:raise ValueError('no training template')
        same=np.array([np.array_equal(t['y'],r['y']) for t in candidates]);matching_target_present+=int(same.any())
        distances={}
        for name,sl in blocks.items():
            x=np.stack([t['x'][sl] for t in candidates]);wanted=r['x'][sl]
            delta=np.sqrt(np.mean((x-wanted)**2,axis=1));order=np.argsort(delta,kind='stable')
            neighbors=[dict(case=candidates[j]['case'],sample=candidates[j]['sample'],generated=candidates[j]['generated'],rms_distance=float(delta[j]),same_target=bool(same[j])) for j in order[:3]]
            distances[name]=dict(nearest=neighbors,nearest_same_target_distance=float(delta[same].min()) if same.any() else None,
                nearest_other_target_distance=float(delta[~same].min()) if (~same).any() else None)
            if name=='full':nearest_same+=int(same[order[0]])
        truth=r['y'][row['quotient']['representatives']]
        results.append(dict(case=r['case'],sample=r['sample'],rule=r['rule'],capture_sha256=r['sha256'],
            metrics=metrics,quotient_truth=truth.tolist(),quotient_scores=scores.tolist(),same_template_training_samples=len(candidates),
            same_target_training_samples=int(same.sum()),distances=distances))
    report=dict(scope='offline direct-source failure support audit on fixed validation inputs',model_sha256=model_sha,decoder_sha256=dr['weights_sha256'],
        training_samples=len(training),direct_validation_samples=sum(not r['generated'] for r in validation),failed_samples=failed,
        failures_with_observed_training_target=matching_target_present,failures_whose_nearest_full_input_has_same_target=nearest_same,
        neighbor_selection_uses_labels=False,training_capture_sha256=sorted({r['sha256'] for r in training}),results=results,
        limitations=['Raw RMS distances are descriptive, not a semantic equivalence or relevance proof','No feature weights, threshold or model are fitted','All instances of the same template are eligible neighbors, including generated-source training samples'])
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
