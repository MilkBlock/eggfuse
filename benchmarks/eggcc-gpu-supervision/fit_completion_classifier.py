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


def fit_head(x,y,alpha=10.):
    # Keep standardization explicit to avoid a large folded intercept cancelling
    # the dense dot product in f32. This is the same closed-form ridge objective.
    mean=x.mean(axis=0);scale=np.maximum(x.std(axis=0),.02)
    z=(x-mean)/scale;bias=y.mean(axis=0)
    dual=np.linalg.solve(z.astype(np.float64)@z.T+alpha*np.eye(len(z)),y-bias)
    return dict(mean=mean,scale=scale,coef=(z.T@dual).astype(np.float32),bias=bias)


def score_head(x,head,xp):
    return ((x-head['mean'])/head['scale'])@head['coef']+head['bias']


def choose(scores,required,states,xp):
    conflict=required.astype(xp.float32)@xp.swapaxes(1-states,-1,-2)
    index=xp.argmax(xp.where(conflict==0,scores,-float('inf')),axis=1)
    return index,states[index]


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
    p.add_argument('--train',type=Path,action='append',required=True);p.add_argument('--validation',type=Path,action='append',required=True);a=p.parse_args()
    with np.load(a.model) as f:model={k:f[k] for k in f.files}
    with np.load(a.source_model) as f:
        for k in ('w','encoding','channels','zero_role_channels'):
            if not np.array_equal(f[k],model[k]):raise ValueError('incompatible feature basis')
    allowed={hashlib.sha256(x.read_bytes()).hexdigest() for x in (a.model,a.source_model)}
    dr=json.loads(a.decoder_report.read_text())
    if dr['model_sha256']!=hashlib.sha256(a.model.read_bytes()).hexdigest() or dr['weights_sha256']!=hashlib.sha256(a.decoder.read_bytes()).hexdigest():raise ValueError('decoder provenance')
    with np.load(a.decoder) as f:
        pick=np.flatnonzero(f['alphas']==dr['selected']['partition'])
        if len(pick)!=1:raise ValueError('decoder selection')
        dw=f['w'];dc=f['coef'][:,pick]
    cases=[];seen=set();family=None;plans=None
    for split,paths in [('train',a.train),('validation',a.validation)]:
        for path in paths:
            d,m=load(path,split)
            if m['model_sha256'] not in allowed or m.get('source_token_mode','exact completed states')!='exact completed states':raise ValueError('unverified exact-source basis')
            sha=m['capture']['program_file_sha256']
            if sha in seen:raise ValueError('duplicate or leaked program')
            seen.add(sha);sf=semantic_family(m)
            if family is not None and sf!=family:raise ValueError('semantic family mismatch')
            if plans is None:plans=[compile_states(r) for r in sf]
            family=sf;d['features'],_=align_features(d,model,True)
            details=inputs_for_case(path,m,d,plans);cases.append((split,d,m,details))
    heads=[];coverage=[]
    for rid,plan in enumerate(plans):
        source=[(d,v[rid]) for s,d,_,v in cases if s=='train' and rid in v]
        x=np.concatenate([d['features'][v['ids']] for d,v in source]);y=np.concatenate([v['target'] for _,v in source])
        heads.append(fit_head(x,y,10.))
        coverage.append(dict(states=y.shape[1],observed_training_states=int(np.any(y,axis=0).sum()),training_instances=len(y)))
    results=[];gpu_error=0.;token_error=0.;decoding_disagreements=0
    for split,d,m,details in cases:
        rebuilt=np.zeros_like(d['targets']);baseline_tokens=np.tanh(d['features']@model['coef']);selected_rows={}
        for rid,v in details.items():
            x=d['features'][v['ids']];score=score_head(x,heads[rid],np);states=plans[rid]['states']
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
        results.append(dict(case=m['capture']['case'],partition=split,sha256=m['capture']['artifact_sha256'],groups=groups,token_decode_disagreements=disagree))
    if gpu_error>5e-6 or token_error>5e-6:raise ValueError(f'GPU numerical error: score={gpu_error}, token={token_error}')
    np.savez_compressed(a.output.with_suffix('.npz'),**{f'head_{i}_{k}':v for i,h in enumerate(heads) for k,v in h.items()})
    out=dict(scope='offline direct whole-state ridge and GPU token reconstruction on real captures; not installed',alpha=10.,backpropagation=False,
        installed=False,union_authorized=False,model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),decoder_sha256=dr['weights_sha256'],
        head_sha256=hashlib.sha256(a.output.with_suffix('.npz').read_bytes()).hexdigest(),coefficient_bytes=sum(h['coef'].nbytes for h in heads),normalization_bytes=sum(h[k].nbytes for h in heads for k in ('mean','scale','bias')),coverage=coverage,
        maximum_gpu_score_error=gpu_error,maximum_gpu_token_error=token_error,token_decode_disagreements=decoding_disagreements,cases=results,
        limitations=['All legal type-compatible states are included, but unseen states have no positive training evidence','No predicted-source rollout or native full-program acceptance','No learned equality is a proof','Current input Eq is retained; scalar effects outside query inputs are unsupported'])
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
