"""Fixed ridge experiment for consumer-relative scalar boundary messages."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from calibrate_semantic_family import load,semantic_family,align_features,corrected
from device_scalar_context import compile_scalar_context,captured_numbers,encode
from audit_input_relations import restore
from audit_snapshot_queries import device
from token_eq_readout import readout_rows,materialize
from audit_training_expansion import summarize
from audit_device_match_readout import dynamic_metrics


def extra_features(path,meta):
    rows=[];max_error=0.;checked=False;nonempty=0
    with np.load(path) as f:
        prefixes=[k[:-4] for k in f.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k]
        prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
        for prefix in prefixes:
            c=restore(f,prefix)
            if not bool(c['recorded']) or not c['accepted'].any():continue
            p=compile_scalar_context(meta['recipe'],int(c['rule']),c['boundary']['slots'].shape[1])
            numbers=captured_numbers(c,meta,p)
            out,count=encode(c['boundary'],c['bindings'],*numbers,p,np)
            rows.extend(out[c['accepted']]);nonempty+=int(np.any(count[c['accepted']]>0,axis=1).sum())
            if not checked and p['consumer_slot']>=0:
                db,di,dn,dp=map(device,(c['boundary'],c['bindings'],numbers,p))
                actual=mx.compile(lambda b,i:encode(b,i,*dn,dp,mx))(db,di);mx.eval(actual)
                max_error=max(float(np.max(abs(out-np.array(actual[0])))),float(np.max(abs(count-np.array(actual[1])))))
                checked=True
    if len(rows)!=meta['capture']['samples'] or not checked or max_error>5e-6:raise ValueError('scalar feature alignment/GPU error')
    return np.array(rows,np.float32),dict(maximum_gpu_error=max_error,nonempty_samples=nonempty)


def main():
    p=argparse.ArgumentParser()
    for key in ('model','capture_model','decoder','decoder_report','output'):p.add_argument(key,type=Path)
    p.add_argument('--train',type=Path,action='append',required=True);p.add_argument('--validation',type=Path,action='append',required=True);a=p.parse_args()
    with np.load(a.model) as f:model={k:f[k] for k in f.files}
    with np.load(a.capture_model) as f:
        for k in ('w','encoding','channels','zero_role_channels'):
            if not np.array_equal(f[k],model[k]):raise ValueError('incompatible capture feature basis')
    allowed={hashlib.sha256(path.read_bytes()).hexdigest() for path in (a.model,a.capture_model)}
    dr=json.loads(a.decoder_report.read_text());decoder_sha=hashlib.sha256(a.decoder.read_bytes()).hexdigest()
    if dr['model_sha256'] not in allowed or decoder_sha!=dr['weights_sha256']:raise ValueError('decoder provenance')
    with np.load(a.decoder) as f:
        idx=np.flatnonzero(f['alphas']==dr['selected']['partition'])
        if len(idx)!=1:raise ValueError('decoder selection')
        dw=f['w'];dc=f['coef'][:,idx]
    cases=[];programs=set();family=None
    for split,paths in [('train',a.train),('validation',a.validation)]:
        for path in paths:
            d,m=load(path,split)
            if m['model_sha256'] not in allowed or m.get('source_token_mode','exact completed states')!='exact completed states':raise ValueError('requires verified exact-source captures')
            identity=m['capture']['program_file_sha256']
            if identity in programs:raise ValueError('duplicate or leaked program')
            programs.add(identity);current=semantic_family(m)
            if family is not None and family!=current:raise ValueError('different semantic family')
            family=current;d['features'],prior=align_features(d,model,True)
            extra,checks=extra_features(path,m);d['conditioned']=np.concatenate([d['features'],extra],axis=1)
            cases.append((split,d,m,checks))
    train=[d for s,d,_,_ in cases if s=='train'];x=np.concatenate([d['features'] for d in train]);cx=np.concatenate([d['conditioned'] for d in train])
    y=np.arctanh(np.clip(np.concatenate([d['targets'] for d in train]),-.999,.999))
    base=corrected(x,y,prior,10.)
    padded=np.concatenate([prior,np.zeros((cx.shape[1]-x.shape[1],prior.shape[1]),np.float32)])
    coef=corrected(cx,y,padded,10.);results=[];gpu_error=0.
    for split,d,m,checks in cases:
        groups={}
        for name,inputs,weights in [('base',d['features'],base),('scalar_conditioned',d['conditioned'],coef)]:
            prediction=np.tanh(inputs@weights)
            actual=mx.tanh(mx.array(inputs)@mx.array(weights));mx.eval(actual)
            gpu_error=max(gpu_error,float(np.max(abs(prediction-np.array(actual)))))
            groups[name]={}
            for group,mask in dict(all=np.ones(len(prediction),bool),direct=~d['generated_source'],generated=d['generated_source']).items():
                rows=[r for r,yes in zip(d['rows'],mask) if yes]
                if not rows:continue
                xx,truth=materialize(readout_rows(rows,True),prediction,dw,True);scores=(xx@dc).ravel()
                groups[name][group]=dict(summarize(rows,scores),dynamic_quotient=dynamic_metrics(truth,scores))
        results.append(dict(case=m['capture']['case'],partition=split,sha256=m['capture']['artifact_sha256'],checks=checks,results=groups))
    if gpu_error>5e-6:raise ValueError('GPU inference discrepancy')
    np.savez_compressed(a.output.with_suffix('.npz'),coef=coef,base_coef=base)
    report=dict(scope='offline scalar-conditioned feature experiment on real multi-entry captures; not installed runtime',alpha=10.,threshold=.5,kernel='exp(-0.5 * actual_numeric_difference**2)',
        backpropagation=False,installed=False,union_authorized=False,trained_samples=len(x),input_columns=cx.shape[1],extra_columns=cx.shape[1]-x.shape[1],coefficient_bytes=coef.nbytes,
        maximum_gpu_prediction_error=gpu_error,allowed_capture_models=sorted(allowed),decoder_sha256=decoder_sha,candidate_sha256=hashlib.sha256(a.output.with_suffix('.npz').read_bytes()).hexdigest(),cases=results,
        limitations=['Validation sets are development data, not final held-out acceptance','Scalar closeness is not an equality proof','Numeric extraction, boundary gathering, scratch and lifecycle costs remain','No predicted-source rollout or speed claim'])
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
