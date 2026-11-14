"""Separate closed-form calibration of semantic Cell prediction and Eq readout.

Training uses one verified partition. Validation never enters either solve.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from fit_union_input_relations import fit
from audit_device_match_readout import rows_from_labels
from token_eq_readout import readout_rows,materialize
from audit_training_expansion import summarize


def load(path,split):
    meta=json.loads(path.with_suffix('.json').read_text());c=meta['capture']
    if c['schema']!='device-joint-witness/v3' or not c['passed'] or c['partition']!=split or hashlib.sha256(path.read_bytes()).hexdigest()!=c['artifact_sha256']:raise ValueError('capture provenance or partition')
    with np.load(path) as f:
        data={k:f[k] for k in ('features','targets','rules','target_eq_classes','generated_source')}
        if 'boundary_features' in f:data['boundary_features']=f['boundary_features']
    ids=[meta['source_rules'].index(int(r)) for r in data['rules']]
    data['rows']=rows_from_labels(meta['semantic_recipe'],ids,data['target_eq_classes'])
    if len(data['features'])!=c['samples'] or not len(data['features']):raise ValueError('sample alignment')
    return data,meta


def corrected(x,y,base,alpha):
    if not np.isfinite(alpha) or alpha<=0 or not np.all(x[:,0]==1):raise ValueError('ridge constant column or alpha')
    delta,bias=fit(x,y-x@base,alpha)
    out=base+delta;out[0]+=bias
    if not np.isfinite(out).all():raise ValueError('nonfinite calibration')
    return out


def semantic_family(meta):
    return [{k:r[k] for k in ('slots','query','effects')} for r in meta['semantic_recipe']['rules'][:len(meta['source_rules'])]]



def align_features(data,model,with_boundary):
    """Accept offline base columns or already assembled live columns once."""
    base=1+model['w'].shape[0]+model['w'].shape[1]
    x=data['features'];coef=model['coef']
    if x.ndim!=2 or not np.isfinite(x).all():raise ValueError('invalid input features')
    if with_boundary:
        extra=data.get('boundary_features')
        if extra is None or extra.ndim!=2 or len(extra)!=len(x) or not extra.shape[1] or not np.isfinite(extra).all():raise ValueError('invalid boundary columns')
        width=base+extra.shape[1]
        if x.shape[1]==base:x=np.concatenate([x,extra],axis=1)
        elif x.shape[1]!=width or not np.array_equal(x[:,base:],extra):raise ValueError('live boundary columns disagree')
        if coef.shape[0]==base:
            if bool(model.get('boundary_context',False)):raise ValueError('boundary model lost coefficients')
            coef=np.concatenate([coef,np.zeros((extra.shape[1],coef.shape[1]),coef.dtype)],axis=0)
        elif coef.shape[0]!=width or not bool(model.get('boundary_context',False)):raise ValueError('model boundary schema')
    elif x.shape[1]!=base or coef.shape[0]!=base or bool(model.get('boundary_context',False)):
        raise ValueError('explicit boundary mode required for live boundary inputs')
    return x,coef


def main():
    p=argparse.ArgumentParser()
    for k in ('training','validation','model','decoder','decoder_report','output_model','output_decoder','output'):p.add_argument(k,type=Path)
    p.add_argument('--extra-training',type=Path,action='append',default=[]);p.add_argument('--boundary-context',action='store_true');p.add_argument('--alpha',type=float,default=10.);a=p.parse_args()
    train,tm=load(a.training,'train');val,vm=load(a.validation,'validation')
    if tm['capture']['program_file_sha256']==vm['capture']['program_file_sha256'] or tm['capture']['case']==vm['capture']['case']:raise ValueError('program leakage')
    family=semantic_family(tm)
    if family!=semantic_family(vm):raise ValueError('different semantic family')
    sha=hashlib.sha256(a.model.read_bytes()).hexdigest();dr=json.loads(a.decoder_report.read_text())
    if any(m['model_sha256']!=sha for m in (tm,vm)) or dr['model_sha256']!=sha or hashlib.sha256(a.decoder.read_bytes()).hexdigest()!=dr['weights_sha256']:raise ValueError('model provenance')
    training_sources=[dict(case=tm['capture']['case'],sha256=tm['capture']['artifact_sha256'],source_token_mode=tm.get('source_token_mode','exact completed states'))]
    seen_programs={tm['capture']['program_file_sha256'],vm['capture']['program_file_sha256']}
    for path in a.extra_training:
        extra,em=load(path,'train')
        if em['model_sha256']!=sha or semantic_family(em)!=family or em['source_rules']!=tm['source_rules']:raise ValueError('additional training family or model')
        if em['capture']['program_file_sha256'] in seen_programs:raise ValueError('duplicate or leaked training program')
        seen_programs.add(em['capture']['program_file_sha256'])
        if set(extra)!=set(train):raise ValueError('training feature schema mismatch')
        train={k:np.concatenate([train[k],extra[k]],axis=0) for k in train if k!='rows'}
        train['rows']=rows_from_labels(tm['semantic_recipe'],[tm['source_rules'].index(int(r)) for r in train['rules']],train['target_eq_classes'])
        training_sources.append(dict(case=em['capture']['case'],sha256=em['capture']['artifact_sha256'],source_token_mode=em.get('source_token_mode','exact completed states')))
    with np.load(a.model) as f:model={k:f[k] for k in f.files}
    with np.load(a.decoder) as f:decoder={k:f[k] for k in f.files}
    selected=np.flatnonzero(decoder['alphas']==dr['selected']['partition'])
    if len(selected)!=1:raise ValueError('decoder column')
    base_decoder=decoder['coef'][:,selected]
    train['features'],base_predictor=align_features(train,model,a.boundary_context)
    val['features'],validation_base=align_features(val,model,a.boundary_context)
    if validation_base.shape!=base_predictor.shape:raise ValueError('training/validation feature width')
    predictor=corrected(train['features'],np.arctanh(np.clip(train['targets'],-.999,.999)),base_predictor,a.alpha)
    dx,dy=materialize(readout_rows(train['rows'],True),train['targets'],decoder['w'],True)
    readout=corrected(dx,dy.astype(np.float32)[:,None],base_decoder,a.alpha)
    # No predicted-token outputs are used to train the readout. This isolates it.
    results={};gpu_error=0.;threshold_disagreements=0
    for predictor_name,tokens in [('cpu_target',val['targets']),('resident',np.tanh(val['features']@base_predictor)),('calibrated',np.tanh(val['features']@predictor))]:
        groups={}
        selectors=dict(all=np.ones(len(tokens),bool),direct=~val['generated_source'],generated=val['generated_source'])
        for name,mask in selectors.items():
            rows=[r for r,yes in zip(val['rows'],mask) if yes]
            if not rows:continue
            x,_=materialize(readout_rows(rows,True),tokens,decoder['w'],True)
            groups[name]={}
            for decoder_name,coef in [('resident',base_decoder),('calibrated',readout)]:
                scores=x@coef;gpu=mx.array(x)@mx.array(coef);mx.eval(gpu);g=np.array(gpu)
                gpu_error=max(gpu_error,float(np.max(abs(g-scores))));threshold_disagreements+=int(np.count_nonzero((g>=.5)!=(scores>=.5)))
                groups[name][decoder_name]=summarize(rows,scores.reshape(-1))
        results[predictor_name]=groups
    gpu=mx.tanh(mx.array(val['features'])@mx.array(predictor));mx.eval(gpu)
    prediction_error=float(np.max(abs(np.array(gpu)-np.tanh(val['features']@predictor))))
    if threshold_disagreements or prediction_error>5e-6:raise ValueError('GPU numerical mismatch')
    training_tokens=np.tanh(train['features']@predictor)
    training_prediction={}
    for name,mask in dict(all=np.ones(len(training_tokens),bool),direct=~train['generated_source'],generated=train['generated_source']).items():
        rows=[r for r,yes in zip(train['rows'],mask) if yes]
        if not rows:continue
        tx,_=materialize(readout_rows(rows,True),training_tokens,decoder['w'],True)
        training_prediction[name]=dict(partition_metrics=summarize(rows,(tx@readout).reshape(-1)),latent_mae=float(np.mean(abs(training_tokens[mask]-train['targets'][mask]))))
    newmodel=dict(model,coef=predictor,boundary_context=a.boundary_context,calibration_training_sources=json.dumps(training_sources,sort_keys=True),family_semantics=json.dumps(family,sort_keys=True),calibration_training_sha256=tm['capture']['artifact_sha256'],calibration_alpha=a.alpha)
    np.savez_compressed(a.output_model,**newmodel)
    newdecoder=dict(decoder,coef=readout,alphas=np.array([a.alpha],np.float32))
    np.savez_compressed(a.output_decoder,**newdecoder)
    model_sha=hashlib.sha256(a.output_model.read_bytes()).hexdigest();decoder_sha=hashlib.sha256(a.output_decoder.read_bytes()).hexdigest()
    a.output_decoder.with_suffix('.json').write_text(json.dumps(dict(model_sha256=model_sha,weights_sha256=decoder_sha,selected=dict(partition=a.alpha),training_sha256=tm['capture']['artifact_sha256'],training_sources=training_sources,scope='semantic family CPU-target calibrated decoder'),indent=2)+'\n')
    nearest=np.array([np.min(np.max(abs(train['features']-x),axis=1)) for x in val['features']])
    output=dict(scope='program-separated semantic-family calibration; not full Eggcc or autonomous learned union',backpropagation=False,alpha=a.alpha,boundary_context=a.boundary_context,feature_columns=train['features'].shape[1],
        training_sources=training_sources,training_case=tm['capture']['case'],validation_case=vm['capture']['case'],training_sha256=tm['capture']['artifact_sha256'],validation_sha256=vm['capture']['artifact_sha256'],
        training_generated_sources=int(train['generated_source'].sum()),training_prediction=training_prediction,training_samples=len(train['features']),validation_samples=len(val['features']),training_distinct_inputs=len(np.unique(train['features'],axis=0)),validation_distinct_inputs=len(np.unique(val['features'],axis=0)),
        validation_inputs_unseen_in_training=int(np.count_nonzero(nearest>1e-5)),validation_generated_sources=int(val['generated_source'].sum()),validation_source_token_mode=vm.get('source_token_mode','exact completed states'),results=results,
        gpu_readout_max_abs=gpu_error,gpu_prediction_max_abs=prediction_error,gpu_threshold_disagreements=threshold_disagreements,
        model_sha256=model_sha,decoder_sha256=decoder_sha,resident_model_sha256=sha,installed=False,
        limitations=['Only three context rules and one validation program','Validation is not held-out test acceptance','Source mode recorded per training program and validation; a newly fitted model still needs its own live feedback replay','Threshold fixed at 0.5; alpha fixed before reading validation results'])
    a.output.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))

if __name__=='__main__':main()
