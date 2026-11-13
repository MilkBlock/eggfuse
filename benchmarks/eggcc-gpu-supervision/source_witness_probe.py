"""Train source-choice robustness from explicit port interfaces; no new graph proof."""
import argparse, hashlib, json, time
from collections import defaultdict
from pathlib import Path
import numpy as np
import mlx.core as mx
from multi_entry_ridge import arrays, features, pooling, projection, metric, replay
from source_moment_probe import load
from whole_cell_ridge import train


def choose(nodes, policy):
    """One observed candidate per input port, never a unique-owner inference.

    Selection uses only input/source metadata. A selected historical observation
    is not necessarily the actual GPU witness or still visible at runtime.
    """
    if policy not in ('first','last','mixed'):raise ValueError('unknown provider policy')
    result=[]
    for ni,node in enumerate(nodes):
        interfaces=node['edge_interfaces'];edges=node['edges']
        if len(interfaces)!=len(edges):raise ValueError('missing port interfaces')
        by_port=defaultdict(list)
        for j,port in enumerate(interfaces):by_port[port['input_slot']].append(j)
        indices=[]
        for port,group in by_port.items():
            if any(interfaces[j]['alternatives']!=len(group) for j in group):raise ValueError('incomplete provider group')
            last=policy=='last' or (policy=='mixed' and (ni+port)%2==1)
            indices.append(group[-1] if last else group[0])
        n=dict(node)
        n['edges']=[(edges[j][0],edges[j][1]*np.sqrt(interfaces[j]['alternatives'])) for j in indices]
        n['edge_routes']=[node['edge_routes'][j] for j in indices]
        n['edge_interfaces']=[dict(interfaces[j],alternatives=1) for j in indices]
        if any(i>=ni or i<0 for i,_ in n['edges']):raise ValueError('noncausal source')
        n['depth']=1+max((result[i]['depth'] for i,_ in n['edges']),default=-1)
        n['multiple']=len({i for i,_ in n['edges']})>1
        result.append(n)
    return result


def inputs(nodes,states,w):
    s,q,_=arrays(nodes)
    return features(s,q,pooling(nodes,states),w,np)


def eq_rows(path):
    from collect_observed_corpus import read_bytes
    from token_eq_readout import examples
    manifest=json.loads(path.read_text());rows=[];offset=0
    for entry in manifest['cases']:
        if entry['status']!='complete':continue
        raw=read_bytes(Path(entry['trace']))
        if hashlib.sha256(raw).hexdigest()!=entry['trace_sha256']:raise ValueError('Eq trace hash')
        nodes,part=examples(json.loads(raw),4,False,True,'class-history-neighborhood-input')
        rows.extend(dict(r,index=r['index']+offset) for r in part);offset+=len(nodes)
    return rows,offset


def eq_audit(rows,tokens,decoder):
    from token_eq_readout import readout_rows,materialize
    from audit_training_expansion import summarize
    totals={}
    for start in range(0,len(rows),128):
        batch=rows[start:start+128]
        x,_=materialize(readout_rows(batch,True),tokens,decoder['w'],True)
        scores=(x@decoder['selected_coef']).reshape(-1)
        for k,v in summarize(batch,scores).items():totals[k]=totals.get(k,0)+v
    return totals


def fixed_alpha_fit(x,y,train_mask,val_mask,alpha):
    if not np.isfinite(alpha) or alpha<=0:raise ValueError('positive finite alpha required')
    mean=x[train_mask].mean(0);mean[0]=0
    scale=np.maximum(x[train_mask].std(0),.02);scale[0]=1
    z=(x-mean)/scale;a=z[train_mask].astype(np.float64);b=y[train_mask].astype(np.float64)
    penalty=np.eye(a.shape[1])*alpha;penalty[0,0]=0
    coef=np.linalg.solve(a.T@a+penalty,a.T@b).astype(np.float32)
    mse=float(np.mean((z[val_mask]@coef-y[val_mask])**2))
    coef=coef/scale[:,None];coef[0]-=(mean[:,None]*coef).sum(0)
    return coef,dict(alpha=alpha,validation_target_mse=mse,fixed_alpha=True)


def main():
    p=argparse.ArgumentParser()
    for k in ('training','validation','model','output'):p.add_argument(k,type=Path)
    p.add_argument('--alpha',type=float);p.add_argument('--decoder',type=Path);p.add_argument('--decoder-report',type=Path)
    a=p.parse_args();started=time.monotonic()
    if bool(a.decoder)!=bool(a.decoder_report):raise ValueError('decoder and report required together')
    tr,tm=load(a.training);va,vm=load(a.validation)
    if tm['partition']!='train' or vm['partition']!='validation' or tm['manifest_sha256']!=vm['manifest_sha256']:raise ValueError('split provenance')
    w=projection(1408);tv=arrays(tr)[2];vv=arrays(va)[2]
    decoder=None;rows=None
    if a.decoder:
        dr=json.loads(a.decoder_report.read_text())
        if hashlib.sha256(a.decoder.read_bytes()).hexdigest()!=dr['weights_sha256']:raise ValueError('decoder hash')
        if dr['provenance']['validation']!=hashlib.sha256(a.validation.read_bytes()).hexdigest():raise ValueError('decoder validation provenance')
        with np.load(a.decoder) as f:decoder={k:f[k] for k in f.files}
        index=np.flatnonzero(decoder['alphas']==dr['selected']['partition'])
        if len(index)!=1:raise ValueError('selected decoder missing')
        decoder['selected_coef']=decoder['coef'][:,index]
        rows,count=eq_rows(a.validation)
        if count!=len(va):raise ValueError('Eq row alignment')
    tvalid=np.array([n['valid'] for n in tr]);vvalid=np.array([n['valid'] for n in va])
    variants={k:choose(va,k) for k in ('first','last','mixed')}
    tx=inputs(tr,tv,w);vx=inputs(va,vv,w)
    tx_single=inputs(choose(tr,'mixed'),tv,w);vx_single=inputs(variants['mixed'],vv,w)
    reports={};models={}
    # Same validation objective for both fits: all-source and mixed single-source.
    # Fit one additional training view only, without changing output semantics.
    for augmented in (False,True):
        train_x=np.concatenate([tx,tx_single]) if augmented else tx
        train_y=np.concatenate([tv,tv]) if augmented else tv
        train_valid=np.tile(tvalid,2 if augmented else 1)
        x=np.concatenate([train_x,vx,vx_single]);y=np.concatenate([train_y,vv,vv])
        valid=np.concatenate([train_valid,vvalid,vvalid]);split=len(train_x)
        args=(x,np.arctanh(np.clip(y,-.999,.999)),valid&(np.arange(len(x))<split),valid&(np.arange(len(x))>=split))
        coef,fit=train(*args) if a.alpha is None else fixed_alpha_fit(*args,a.alpha)
        del x,y
        label='augmented' if augmented else 'baseline';models[label]=coef
        modes={}
        for policy,view in [('all',va),('first',variants['first']),('last',variants['last'])]:
            matrix=inputs(view,vv,w);direct=np.tanh(matrix@coef)
            rolled=replay(view,w,coef,True)
            gpu=mx.tanh(mx.array(matrix)@mx.array(coef));mx.eval(gpu)
            modes[policy]=dict(direct=metric(direct,vv,vvalid),rollout=metric(rolled,vv,vvalid),
                gpu_direct_max_abs=float(np.max(abs(np.array(gpu)-direct))))
            if decoder is not None:
                modes[policy]['eq_direct']=eq_audit(rows,direct,decoder)
                modes[policy]['eq_rollout']=eq_audit(rows,rolled,decoder)
        reports[label]=dict(fit=fit,modes=modes)
    # Artifact is experimental, not installed into the resident runtime.
    with a.model.open('wb') as f:
        np.savez_compressed(f,w=w,coef=models['augmented'],channels=4,zero_role_channels=False,
            encoding='class-history-neighborhood-input',source_neighborhood=False,source_relations=False,
            provider_training='all-plus-mixed-single')
    ambiguous=sum(any(p['alternatives']>1 for p in n['edge_interfaces']) for n in va)
    result=dict(scope='observed port-interface witness-choice ablation; not autonomous execution or semantic accuracy',
        backpropagation=False,corpus_sha256=tm['manifest_sha256'],
        training_manifest_sha256=hashlib.sha256(a.training.read_bytes()).hexdigest(),
        validation_manifest_sha256=hashlib.sha256(a.validation.read_bytes()).hexdigest(),
        validation_instances=len(va),validation_ambiguous_source_instances=ambiguous,
        validation_all_edges=sum(len(n['edges']) for n in va),validation_single_edges=sum(len(n['edges']) for n in variants['first']),
        reports=reports,model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),seconds=time.monotonic()-started,
        additional_inference_features=0,decoder_sha256=hashlib.sha256(a.decoder.read_bytes()).hexdigest() if a.decoder else None,
        limitations=['Observed alternatives are not lifetime certificates or unique owners',
            'Portwise choice need not be a jointly realizable GPU query witness',
            'GPU runs floating rollout on supplied wiring, not the full ruleset controller',
            'RMSE is not exact Eq accuracy; test partition not consulted; resident model unchanged'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
