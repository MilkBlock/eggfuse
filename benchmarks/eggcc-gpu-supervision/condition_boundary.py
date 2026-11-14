"""Train role-conditioned boundary ridge and fold static gates into coefficients.

No gradients or rule-ID embeddings. Saved exact-source inputs are reused; no
query/effect path is replaced by this offline model experiment.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from calibrate_semantic_family import load,semantic_family,align_features,corrected
from device_semantic_template import semantic,template
from audit_device_match_readout import dynamic_metrics
from token_eq_readout import readout_rows,materialize
from audit_training_expansion import summarize


def gate(rule,width,hidden=32):
    rule,_=semantic(rule)
    if len(rule['slots'])>width:raise ValueError('gate slot width')
    roles,_=template(rule)
    weight=np.random.default_rng(20261118).normal(0,1/8,(64,hidden)).astype(np.float32)
    out=np.zeros((width,hidden),np.float32)
    for i,s in enumerate(rule['slots']):
        if s['definition']=='query' and s['sort']['kind']=='eq':out[i]=np.tanh(roles[i]@weight)
    return np.tile(out.reshape(-1),2)


def fold(coef,static_gate,base_width):
    width=len(static_gate);n=base_width+width
    if coef.shape[0]!=n+width:raise ValueError('conditioned coefficient width')
    out=coef[:n].copy();out[base_width:]+=static_gate[:,None]*coef[n:]
    return out



def captured_bridges(path,meta,shared_context=False,mean_context=False):
    from audit_input_relations import restore
    from device_boundary_context import compile_context
    from device_boundary_bridges import compile_pairs,encode
    if shared_context:
        from device_boundary_shared_context import encode
    from audit_snapshot_queries import device
    values=[];max_error=0.;checked=False
    with np.load(path) as f:
        prefixes=[k[:-4] for k in f.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k]
        prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
        for prefix in prefixes:
            c=restore(f,prefix)
            if not bool(c['recorded']) or not c['accepted'].any():continue
            plan=compile_context(meta['recipe'],int(c['rule']),c['boundary']['slots'].shape[1]);plan['mean_context']=mean_context;pairs=compile_pairs(plan)
            out,count=encode(c['boundary'],c['bindings'],plan,pairs,np)
            values.extend(out[c['accepted']])
            if not checked:
                db,di,dp,dq=map(device,(c['boundary'],c['bindings'],plan,pairs))
                actual=mx.compile(lambda x:encode(x,di,dp,dq,mx))(db);mx.eval(actual)
                max_error=float(np.max(abs(np.array(actual[0])-out)));np.testing.assert_array_equal(np.array(actual[1]),count);checked=True
    if len(values)!=meta['capture']['samples'] or max_error>5e-6:raise ValueError('bridge capture/GPU mismatch')
    return np.array(values,np.float32),max_error


def main():
    p=argparse.ArgumentParser()
    for k in ('model','decoder','decoder_report','output'):p.add_argument(k,type=Path)
    p.add_argument('--train',type=Path,action='append',required=True);p.add_argument('--validation',type=Path,action='append',required=True)
    p.add_argument('--capture-model',type=Path,action='append',default=[]);a=p.parse_args()
    with np.load(a.model) as f:model={k:f[k] for k in f.files}
    base_width=1+model['w'].shape[0]+model['w'].shape[1]
    if model['coef'].shape[0]!=base_width:raise ValueError('start from resident base model')
    allowed={hashlib.sha256(a.model.read_bytes()).hexdigest()}
    for path in a.capture_model:
        with np.load(path) as f:
            for key in ('w','encoding','channels','zero_role_channels'):
                if not np.array_equal(f[key],model[key]):raise ValueError('different feature basis')
        allowed.add(hashlib.sha256(path.read_bytes()).hexdigest())
    report=json.loads(a.decoder_report.read_text())
    if report['model_sha256'] not in allowed or hashlib.sha256(a.decoder.read_bytes()).hexdigest()!=report['weights_sha256']:raise ValueError('decoder provenance')
    with np.load(a.decoder) as f:dw=f['w'];dc=f['coef'][:,np.flatnonzero(f['alphas']==report['selected']['partition'])]
    if dc.shape[1]!=1:raise ValueError('decoder selection')
    cases=[];family=None;programs=set();bridge_error=0.
    for split,paths in [('train',a.train),('validation',a.validation)]:
        for path in paths:
            d,m=load(path,split)
            if m['model_sha256'] not in allowed or m.get('source_token_mode','exact completed states')!='exact completed states':raise ValueError('unverified exact-source feature basis')
            sha=m['capture']['program_file_sha256']
            if sha in programs:raise ValueError('duplicate or leaked program')
            programs.add(sha);current=semantic_family(m)
            if family is not None and current!=family:raise ValueError('different Cell family')
            family=current;d['features'],prior=align_features(d,model,True)
            width=d['boundary_features'].shape[1]//64
            if width*64!=d['boundary_features'].shape[1]:raise ValueError('boundary layout')
            gates=np.stack([gate(r,width) for r in family])
            ids=np.array([m['source_rules'].index(int(r)) for r in d['rules']])
            extra=d['boundary_features']*gates[ids]
            d['conditioned']=np.concatenate([d['features'],extra],axis=1)
            bridge,error=captured_bridges(path,m);bridge_error=max(bridge_error,error)
            d['bridges']=np.concatenate([d['features'],bridge],axis=1)
            cases.append((split,d,m,ids,gates))
    training=[c for c in cases if c[0]=='train']
    x=np.concatenate([d['features'] for _,d,_,_,_ in training]);cx=np.concatenate([d['conditioned'] for _,d,_,_,_ in training])
    y=np.concatenate([d['targets'] for _,d,_,_,_ in training]);target=np.arctanh(np.clip(y,-.999,.999))
    base=corrected(x,target,prior,10.)
    bx=np.concatenate([d['bridges'] for _,d,_,_,_ in training])
    bridge_prior=np.concatenate([prior,np.zeros((bx.shape[1]-x.shape[1],prior.shape[1]),prior.dtype)],axis=0)
    bridge_coef=corrected(bx,target,bridge_prior,10.)
    augmented_prior=np.concatenate([prior,np.zeros((cx.shape[1]-x.shape[1],prior.shape[1]),prior.dtype)],axis=0)
    conditioned=corrected(cx,target,augmented_prior,10.)
    training_ids=np.concatenate([ids for _,_,_,ids,_ in training])
    per_cell=[]
    for rid in range(len(family)):
        selected=training_ids==rid
        if not selected.any():raise ValueError('Cell has no training evidence')
        per_cell.append(corrected(x[selected],target[selected],prior,10.))
    per_cell=np.stack(per_cell)
    results=[];max_fold=0.;max_gpu=0.
    for split,d,m,ids,gates in cases:
        folded=np.empty_like(d['targets']);local=np.empty_like(d['targets'])
        for rid in np.unique(ids):
            mask=ids==rid;coef=fold(conditioned,gates[rid],base_width)
            folded[mask]=np.tanh(d['features'][mask]@coef)
            local[mask]=np.tanh(d['features'][mask]@per_cell[rid])
            gpu=mx.tanh(mx.array(d['features'][mask])@mx.array(coef));mx.eval(gpu)
            max_gpu=max(max_gpu,float(np.max(abs(np.array(gpu)-folded[mask]))))
            gpu=mx.tanh(mx.array(d['features'][mask])@mx.array(per_cell[rid]));mx.eval(gpu)
            max_gpu=max(max_gpu,float(np.max(abs(np.array(gpu)-local[mask]))))
        explicit=np.tanh(d['conditioned']@conditioned);max_fold=max(max_fold,float(np.max(abs(explicit-folded))))
        groups={}
        for name,tokens in [('base',np.tanh(d['features']@base)),('conditioned',folded),('per_cell',local),('bridges',np.tanh(d['bridges']@bridge_coef))]:
            if name=='bridges':
                gpu=mx.tanh(mx.array(d['bridges'])@mx.array(bridge_coef));mx.eval(gpu)
                max_gpu=max(max_gpu,float(np.max(abs(np.array(gpu)-tokens))))
            groups[name]={}
            for group,mask in dict(all=np.ones(len(ids),bool),direct=~d['generated_source'],generated=d['generated_source']).items():
                rows=[row for row,yes in zip(d['rows'],mask) if yes]
                if not rows:continue
                xx,truth=materialize(readout_rows(rows,True),tokens,dw,True);scores=(xx@dc).ravel()
                groups[name][group]=dict(summarize(rows,scores),dynamic_quotient=dynamic_metrics(truth,scores))
        results.append(dict(case=m['capture']['case'],partition=split,sha256=m['capture']['artifact_sha256'],results=groups))
    if max_fold>5e-6 or max_gpu>5e-6:raise ValueError('fold/GPU numerical error')
    a.output.with_suffix('.npz').parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(a.output.with_suffix('.npz'),coef=conditioned,base_coef=base,per_cell_coef=per_cell,bridge_coef=bridge_coef,gate=gates,base_width=base_width)
    out=dict(scope='offline consumer-role and shared-neighbor experiments on actual exact-source captures; not installed runtime',alpha=10.,threshold=.5,backpropagation=False,installed=False,source_model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),allowed_capture_models=sorted(allowed),candidate_weights_sha256=hashlib.sha256(a.output.with_suffix('.npz').read_bytes()).hexdigest(),
        maximum_bridge_gpu_error=bridge_error,bridge_runtime_columns=bx.shape[1],bridge_coefficients_bytes=bridge_coef.nbytes,trained_samples=len(x),new_runtime_feature_columns_after_fold=0,explicit_training_columns=cx.shape[1],runtime_input_columns=x.shape[1],
        per_cell_coefficients_bytes=per_cell.nbytes,shared_prefix_bytes=conditioned[:base_width].nbytes,folded_boundary_bytes=len(family)*(x.shape[1]-base_width)*conditioned.shape[1]*conditioned.dtype.itemsize,
        maximum_fold_error=max_fold,maximum_gpu_error=max_gpu,decoder_sha256=report['weights_sha256'],cases=results,
        limitations=['Validation cases are not a final held-out test','Static folding removes feature multiplication, not query/ownership work','GPU folding check excludes dispatch, upload and lifecycle costs','No predicted-source rollout or trained model adoption in this experiment'])
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
