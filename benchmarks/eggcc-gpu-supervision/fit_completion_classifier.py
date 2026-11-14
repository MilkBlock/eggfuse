"""Closed-form whole-state ridge head with actual dynamic scalar token synthesis.

All type-compatible states are compiled independently of labels. Only state-score
coefficients are fitted. This experiment is not installed or union authority.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from calibrate_semantic_family import load,semantic_family,align_features
from audit_completion_states import captured_inputs
from device_completion_states import compile_states,compile_tokens,tokens
from audit_snapshot_queries import device
from multi_entry_ridge import scalar
from audit_training_expansion import summarize
from audit_device_match_readout import dynamic_metrics
from token_eq_readout import readout_rows,materialize
from device_completion_classifier import score_head,choose,classifier_features
from completion_control import capture_control


def fit_head(x,y,alpha=10.,weights=None):
    # Keep standardization explicit to avoid a large folded intercept cancelling
    # the dense dot product in f32. This is the same closed-form ridge objective.
    if weights is not None:
        weights=np.asarray(weights,np.float64)
        if weights.shape!=(len(x),) or not np.isfinite(weights).all() or np.any(weights<=0):raise ValueError('positive finite row weights required')
        weights=weights/weights.mean()
        mean=np.average(x,axis=0,weights=weights).astype(np.float32)
        scale=np.maximum(np.sqrt(np.average((x-mean).astype(np.float64)**2,axis=0,weights=weights)),.02).astype(np.float32)
        bias=np.average(y,axis=0,weights=weights).astype(np.float32)
        z=(x-mean)/scale;root=np.sqrt(weights)
        a=z.astype(np.float64)*root[:,None];b=(y-bias)*root[:,None]
        dual=np.linalg.solve(a@a.T+alpha*np.eye(len(a)),b)
        return dict(mean=mean,scale=scale,coef=(a.T@dual).astype(np.float32),bias=bias)
    mean=x.mean(axis=0);scale=np.maximum(x.std(axis=0),.02)
    z=(x-mean)/scale;bias=y.mean(axis=0)
    dual=np.linalg.solve(z.astype(np.float64)@z.T+alpha*np.eye(len(z)),y-bias)
    return dict(mean=mean,scale=scale,coef=(z.T@dual).astype(np.float32),bias=bias)




def fit_normalized_joint_head(x,y,alpha=10.,weights=None,hidden=256):
    from device_joint_features import compile_projection
    mean=x.mean(axis=0);scale=np.maximum(x.std(axis=0),.02)
    projection=compile_projection(x.shape[1],hidden)/scale[:,None]
    projection[np.min(x,axis=0)==np.max(x,axis=0)]=0  # No observed variation; retain raw columns, omit nonlinear amplification.
    basis=dict(feature_projection=projection,feature_center=mean)
    expanded=classifier_features(x,basis,np)
    return dict(fit_head(expanded,y,alpha,weights),**basis)


def balanced_state_weights(y):
    if y.ndim!=2 or not np.all((y==0)|(y==1)) or not np.all(y.sum(axis=1)==1):raise ValueError('one-hot states required')
    counts=y.sum(axis=0);labels=y.argmax(axis=1)
    w=1/counts[labels]
    return w/w.mean()


def source_group(meta):
    c=meta['capture']
    return ('synthetic:'+c['input_sha256']) if c.get('synthetic_input') else c['program_file_sha256']


def training_policy(meta, allow_historical=False):
    if not meta['capture'].get('synthetic_input') and not allow_historical:
        raise ValueError('real Run training disabled; use rule-generated synthetic inputs')


def feedback_head_identity(path):
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    report=json.loads(path.with_suffix('.json').read_text())
    if report.get('head_sha256')!=sha or report.get('synthetic_only_training') is not True:
        raise ValueError('feedback head must have a matching synthetic-only training report')
    return sha


def verify_source(meta, allowed_models, feedback_heads):
    if meta['model_sha256'] not in allowed_models:raise ValueError('unverified feature basis')
    mode=meta.get('source_token_mode','exact completed states')
    if mode=='exact completed states':return
    info=meta.get('completion_readout') or {}
    if (not meta['capture'].get('synthetic_input') or mode!='direct state ridge generated Cells, exact imported Cells'
        or info.get('kind')!='direct_state_ridge' or info.get('head_sha256') not in feedback_heads):
        raise ValueError('unverified synthetic feedback source')


def register_entry(meta, split, programs, entries):
    """Allow distinct training snapshots, never cross-program-split leakage."""
    program=source_group(meta)
    if program in programs and (programs[program]!=split or split!='train'):
        raise ValueError('duplicate validation or leaked program')
    entry=(program,meta['snapshot_run'],meta.get('source_token_mode','exact completed states'),bool(meta.get('producer_frame_import')))
    if entry in entries:raise ValueError('duplicate program entry')
    programs[program]=split;entries.add(entry)


def unique_training_rows(x,y,programs):
    # Same input in different programs remains independent evidence. Within a
    # program, repeated entries must not increase its weight by recapture alone.
    seen={};keep=[];conflicts=0
    for i,(row,target,program) in enumerate(zip(x,y,programs)):
        key=(program,row.tobytes());label=target.tobytes()
        if key in seen:
            old=seen[key]
            if label in old:continue
            conflicts+=1;old.add(label)
        else:seen[key]={label}
        keep.append(i)
    return x[keep],y[keep],dict(captured=len(x),unique=len(keep),duplicates=len(x)-len(keep),ambiguous_inputs=conflicts)


def ambiguous_rows(required,states):
    allowed=~np.any(required[:,None,:]&~states.astype(bool)[None,:,:],axis=2)
    if np.any(allowed.sum(axis=1)==0):raise ValueError('input constraints have no legal completion')
    return allowed.sum(axis=1)>1


def feature_conflicts(x,y):
    # Cross-source information check, unlike per-program weighting deduplication.
    groups={}
    for row,target in zip(x,y):
        row=row.copy();row[row==0]=0
        groups.setdefault(row.tobytes(),set()).add(target.tobytes())
    return dict(unique_inputs=len(groups),conflicting_groups=sum(len(v)>1 for v in groups.values()),includes_required_eq_mask=False)


def assemble_classifier_features(path,meta,data,model,shared_context=False,joint_features=False,mean_context=False,local_context=False):
    from condition_boundary import captured_bridges
    from device_joint_features import compile_projection,expand
    info=meta.get('completion_readout') or {}
    captured_shared=bool(info.get('shared_boundary_context',False))
    captured_joint=bool(info.get('joint_features',False))
    base=1+model['w'].shape[0]+model['w'].shape[1]+data['boundary_features'].shape[1]
    raw=data['features'];error=0.;extra=None
    if shared_context or captured_shared:
        extra,error=captured_bridges(path,meta,shared_context=True,mean_context=mean_context if shared_context else bool(info.get('mean_shared_context',False)),local_context=local_context if shared_context else bool(info.get('local_shared_context',False)))
    expected=base+(extra.shape[1] if captured_shared else 0)+(256 if captured_joint else 0)
    if raw.shape[1]!=expected:raise ValueError('capture extension schema mismatch')
    prefix=raw[:,:base]
    check=prefix
    if captured_shared:
        captured_extra=extra
        if shared_context and (mean_context!=bool(info.get('mean_shared_context',False)) or local_context!=bool(info.get('local_shared_context',False))):
            captured_extra,captured_error=captured_bridges(path,meta,shared_context=True,mean_context=bool(info.get('mean_shared_context',False)),local_context=bool(info.get('local_shared_context',False)))
            error=max(error,captured_error)
        check=np.concatenate([check,captured_extra],axis=1)
    if captured_joint:check=expand(check,compile_projection(check.shape[1]),np)
    if not np.allclose(raw,check,atol=5e-6,rtol=0):raise ValueError('captured feature extension mismatch')
    data['features']=prefix
    data['features'],_=align_features(data,model,True)
    x=data['features']
    if shared_context:x=np.concatenate([x,extra],axis=1)
    if joint_features:x=expand(x,compile_projection(x.shape[1]),np)
    return x,error


def inputs_for_case(path,meta,data,plans):
    captures=captured_inputs(path,meta);out={}
    if len(captures)!=len(data['rules']):raise ValueError('capture alignment')
    for rid in np.unique(data['rules']):
        local=meta['source_rules'].index(int(rid));rule=meta['semantic_recipe']['rules'][local]
        plan=plans[local];tp=compile_tokens(rule,plan);ids=np.flatnonzero(data['rules']==rid)
        required=np.zeros((len(ids),plan['states'].shape[1]),bool);codes=[]
        for lane,i in enumerate(ids):
            source,b=captures[i]
            if source!=int(rid):raise ValueError('capture rule alignment')
            for (a,z),q in zip(plan['pairs'],plan['quotient']['expansion']):
                if q>=0 and all(rule['slots'][s]['definition']=='query' and b['slot_valid'][s] for s in (a,z)):
                    if b['slot_roots'][a]<0 or b['slot_roots'][z]<0:raise ValueError('invalid input root')
                    required[lane,q]|=b['slot_roots'][a]==b['slot_roots'][z]
            values=[]
            for s in tp['scalar_slots']:
                if rule['slots'][s]['definition']!='query' or not b['slot_valid'][s]:raise ValueError('unexecuted scalar effect')
                v=meta['seed_scalars'][str(int(b['slots'][s]))]
                if v['sort']!=rule['slots'][s]['sort']['name'] or 'eq' in v:raise ValueError('scalar type')
                values.append(scalar(v))
            codes.append(values)
        truth=np.stack([data['rows'][i]['y'][plan['quotient']['representatives']] for i in ids])
        if np.any(required&~truth):raise ValueError('input proof contradicts final state')
        # Labels determine targets only; neither state construction nor input constraints.
        matches=np.all(truth[:,None,:]==plan['states'][None,:,:],axis=-1)
        if not np.all(matches.sum(axis=1)==1):raise ValueError('target state coverage')
        out[local]=dict(ids=ids,required=required,codes=np.array(codes,np.float32).reshape(len(ids),len(tp['scalar_slots']),64),target=matches.astype(np.float32),token_plan=tp)
    return out


def main():
    p=argparse.ArgumentParser()
    for key in ('model','source_model','decoder','decoder_report','output'):p.add_argument(key,type=Path)
    p.add_argument('--normalized-joint',action='store_true',help='training-input standardized fixed nonlinear projection; no gradients')
    p.add_argument('--normalized-width',type=int,default=256,help='fixed nonlinear columns for normalized joint ridge')
    p.add_argument('--local-context',action='store_true',help='anchor shared context on constructor-result sorts')
    p.add_argument('--ambiguous-only',action='store_true',help='fit only rows whose input constraints permit multiple completion states')
    p.add_argument('--mean-context',action='store_true',help='mean rather than sqrt-count normalization in shared context')
    p.add_argument('--joint-features',action='store_true',help='fixed 256-column nonlinear input/context mixing')
    p.add_argument('--balanced-states',action='store_true',help='equal total training weight per observed completion state')
    p.add_argument('--shared-context',action='store_true',help='append current-boundary floating shared context; offline experimental head')
    p.add_argument('--feedback-head',type=Path,action='append',default=[],help='explicit parent weights for audited synthetic feedback')
    p.add_argument('--allow-historical-real-training',action='store_true',help='explicit historical experiment reproduction only')
    p.add_argument('--train',type=Path,action='append',required=True);p.add_argument('--validation',type=Path,action='append',required=True);a=p.parse_args()
    if a.normalized_width<1 or (a.normalized_width!=256 and not a.normalized_joint):raise ValueError('normalized width requires normalized joint and positive dimensions')
    if a.normalized_joint and a.joint_features:raise ValueError('choose one joint projection')
    if (a.mean_context or a.local_context) and not a.shared_context:raise ValueError('mean/local context requires shared context')
    with np.load(a.model) as f:model={k:f[k] for k in f.files}
    with np.load(a.source_model) as f:
        for k in ('w','encoding','channels','zero_role_channels'):
            if not np.array_equal(f[k],model[k]):raise ValueError('incompatible feature basis')
    feedback_heads={feedback_head_identity(p) for p in a.feedback_head}
    allowed={hashlib.sha256(x.read_bytes()).hexdigest() for x in (a.model,a.source_model)}
    dr=json.loads(a.decoder_report.read_text())
    if dr['model_sha256']!=hashlib.sha256(a.model.read_bytes()).hexdigest() or dr['weights_sha256']!=hashlib.sha256(a.decoder.read_bytes()).hexdigest():raise ValueError('decoder provenance')
    with np.load(a.decoder) as f:
        pick=np.flatnonzero(f['alphas']==dr['selected']['partition'])
        if len(pick)!=1:raise ValueError('decoder selection')
        dw=f['w'];dc=f['coef'][:,pick]
    cases=[];programs={};entries=set();family=None;plans=None;completion_control=None;context_error=0.
    for split,paths in [('train',a.train),('validation',a.validation)]:
        for path in paths:
            d,m=load(path,split)
            if split=='train':training_policy(m,a.allow_historical_real_training)
            verify_source(m,allowed,feedback_heads)
            contract=capture_control(m)
            if completion_control is not None and contract!=completion_control:raise ValueError('mixed completion control contracts')
            completion_control=contract
            register_entry(m,split,programs,entries);sf=semantic_family(m)
            if family is not None and sf!=family:raise ValueError('semantic family mismatch')
            if plans is None:plans=[compile_states(r) for r in sf]
            family=sf
            d['classifier_features'],error=assemble_classifier_features(path,m,d,model,a.shared_context,a.joint_features,a.mean_context,a.local_context)
            context_error=max(context_error,error)
            details=inputs_for_case(path,m,d,plans);cases.append((split,d,m,details))
    heads=[];coverage=[]
    for rid,plan in enumerate(plans):
        source=[(d,v[rid],source_group(m)) for s,d,m,v in cases if s=='train' and rid in v]
        x=np.concatenate([d['classifier_features'][v['ids']] for d,v,_ in source]);y=np.concatenate([v['target'] for _,v,_ in source])
        programs_for_rows=[p for _,v,p in source for _ in v['ids']]
        forced=0
        if a.ambiguous_only:
            required=np.concatenate([v['required'] for _,v,_ in source])
            keep=ambiguous_rows(required,plan['states']);forced=int((~keep).sum())
            x=x[keep];y=y[keep];programs_for_rows=[p for p,k in zip(programs_for_rows,keep) if k]
            if not len(x):raise ValueError('no ambiguous examples for this head')
        x,y,duplicates=unique_training_rows(x,y,programs_for_rows)
        weights=balanced_state_weights(y) if a.balanced_states else None
        heads.append(fit_normalized_joint_head(x,y,10.,weights=weights,hidden=a.normalized_width) if a.normalized_joint else fit_head(x,y,10.,weights=weights))
        coverage.append(dict(input_determined_rows_excluded=forced,states=y.shape[1],observed_training_states=int(np.any(y,axis=0).sum()),training_instances=len(y),sampling=duplicates,exact_feature_conflicts=feature_conflicts(x,y)))
    results=[];gpu_error=0.;token_error=0.;decoding_disagreements=0
    for split,d,m,details in cases:
        rebuilt=np.zeros_like(d['targets']);baseline_tokens=np.tanh(d['features']@model['coef']);selected_rows={}
        for rid,v in details.items():
            x=d['classifier_features'][v['ids']];score=score_head(x,heads[rid],np);states=plans[rid]['states']
            index,chosen=choose(score,v['required'],states,np)
            rebuilt[v['ids']]=tokens(index,v['codes'],v['token_plan'],np)
            dh,ds,drq,dt,dsco=map(device,(heads[rid],states,v['required'],v['token_plan'],v['codes']))
            def kernel(xx):
                ss=score_head(xx,dh,mx);ii,cc=choose(ss,drq,ds,mx)
                return ss,ii,cc,tokens(ii,dsco,dt,mx)
            gs,gi,gc,gt=mx.compile(kernel)(mx.array(x));mx.eval(gs,gi,gc,gt)
            gpu_error=max(gpu_error,float(np.max(abs(np.array(gs)-score))))
            np.testing.assert_array_equal(gi,index);np.testing.assert_array_equal(gc,chosen)
            token_error=max(token_error,float(np.max(abs(np.array(gt)-rebuilt[v['ids']]))))
            for i,row in zip(v['ids'],chosen):selected_rows[int(i)]=row
        all_scores=np.concatenate([selected_rows[i] for i in range(len(rebuilt))]);groups={}
        cuts=np.cumsum([0]+[len(selected_rows[i]) for i in range(len(rebuilt))])
        xx,truth=materialize(readout_rows(d['rows'],True),rebuilt,dw,True);decoded=(xx@dc).ravel()
        disagree=int(np.count_nonzero((decoded>=.5)!=(all_scores>=.5)));decoding_disagreements+=disagree
        for group,mask in dict(all=np.ones(len(rebuilt),bool),direct=~d['generated_source'],generated=d['generated_source']).items():
            rows=[row for row,yes in zip(d['rows'],mask) if yes]
            if not rows:continue
            ids=np.concatenate([np.arange(cuts[i],cuts[i+1]) for i in np.flatnonzero(mask)])
            bx,by=materialize(readout_rows(rows,True),baseline_tokens,dw,True);bs=(bx@dc).ravel()
            groups[group]=dict(baseline=dict(summarize(rows,bs),dynamic_quotient=dynamic_metrics(by,bs)),
                classifier=dict(summarize(rows,all_scores[ids]),dynamic_quotient=dynamic_metrics(truth[ids],all_scores[ids])))
        results.append(dict(case=m['capture']['case'],partition=split,snapshot_run=m['snapshot_run'],sha256=m['capture']['artifact_sha256'],groups=groups,token_decode_disagreements=disagree))
    if gpu_error>5e-6 or token_error>5e-6:raise ValueError(f'GPU numerical error: score={gpu_error}, token={token_error}')
    np.savez_compressed(a.output.with_suffix('.npz'),**{f'head_{i}_{k}':v for i,h in enumerate(heads) for k,v in h.items()})
    out=dict(scope='offline direct whole-state ridge and GPU token reconstruction on audited GPU captures; not installed',alpha=10.,backpropagation=False,
        installed=False,union_authorized=False,normalized_joint=a.normalized_joint,normalized_width=a.normalized_width if a.normalized_joint else None,local_shared_context=a.local_context,ambiguous_only=a.ambiguous_only,mean_shared_context=a.mean_context,joint_features=a.joint_features,balanced_states=a.balanced_states,shared_boundary_context=a.shared_context,maximum_gpu_context_error=context_error,completion_control=completion_control,training_source_groups=sum(v=='train' for v in programs.values()),synthetic_only_training=all(m['capture'].get('synthetic_input',False) for s,_,m,_ in cases if s=='train'),feedback_parent_heads=sorted(feedback_heads),training_entries=sum(s=='train' for s,_,_,_ in cases),model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),decoder_sha256=dr['weights_sha256'],
        head_sha256=hashlib.sha256(a.output.with_suffix('.npz').read_bytes()).hexdigest(),coefficient_bytes=sum(h['coef'].nbytes for h in heads),feature_projection_bytes=sum(h[k].nbytes for h in heads for k in ('feature_projection','feature_center') if k in h),normalization_bytes=sum(h[k].nbytes for h in heads for k in ('mean','scale','bias')),coverage=coverage,
        maximum_gpu_score_error=gpu_error,maximum_gpu_token_error=token_error,token_decode_disagreements=decoding_disagreements,cases=results,
        limitations=['All legal type-compatible states are included, but unseen states have no positive training evidence','No predicted-source rollout or native full-program acceptance','No learned equality is a proof','Current input Eq is retained; scalar effects outside query inputs are unsupported'])
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
