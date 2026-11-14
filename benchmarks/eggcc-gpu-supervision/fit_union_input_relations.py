"""Program-separated closed-form residual ridge ablation on actual GPU witnesses.

Experimental weights only. No future target enters feature construction, no
backpropagation, and no prediction authorizes union.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from audit_input_relations import restore
from device_input_relations import inputs,encode,projection
from device_match_capture import audit
from audit_device_match_readout import rows_from_labels
from source_witness_probe import eq_audit


def load(record):
    path=Path(record['capture']);meta=json.loads(path.with_suffix('.json').read_text())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=record['artifact_sha256'] or not meta['capture']['passed']:raise ValueError('unverified capture')
    if meta['capture']['partition']!=record['partition'] or meta['capture']['case']!=record['case']:raise ValueError('capture partition')
    if meta['capture']['schema']!='device-joint-witness/v2':raise ValueError('capture schema')
    extra=[]
    with np.load(path) as f:
        # Match the writer's numeric tick/inner/block order, not string order.
        prefixes=[k[:-len('rule')] for k in f.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k]
        prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
        for prefix in prefixes:
            c=restore(f,prefix)
            if not bool(c['recorded']):continue
            if not audit(meta['recipe'],c)['passed']:raise ValueError('invalid source witness')
            x=inputs(meta['recipe'],c);z,_=encode(x,projection(),np)
            extra.extend(z[c['accepted']])
        if len(extra)!=len(f['features']):raise ValueError('sample alignment')
        rid=[meta['source_rules'].index(int(r)) for r in f['rules']]
        rows=rows_from_labels(meta['recipe'],rid,f['target_eq_classes'])
        return f['features'].copy(),np.array(extra,np.float32),f['targets'].copy(),rows


def fit(x,y,alpha):
    # Dual ridge: solve training-instance matrix rather than the wide feature Gram.
    mean=x.mean(0);scale=np.maximum(x.std(0),.02)
    z=(x-mean)/scale;ym=y.mean(0);center=y-ym
    dual=np.linalg.solve(z.astype(np.float64)@z.T+alpha*np.eye(len(z)),center)
    coef=(z.T@dual).astype(np.float32)/scale[:,None]
    bias=ym-mean@coef
    return coef,bias


def main():
    p=argparse.ArgumentParser()
    for k in ('corpus','model','decoder','decoder_report','weights','output'):p.add_argument(k,type=Path)
    a=p.parse_args();corpus=json.loads(a.corpus.read_text())
    if not corpus['passed']:raise ValueError('incomplete corpus')
    with np.load(a.model) as f:resident=f['coef']
    if hashlib.sha256(a.model.read_bytes()).hexdigest()!=corpus['model_sha256']:raise ValueError('parent model')
    dr=json.loads(a.decoder_report.read_text())
    if hashlib.sha256(a.decoder.read_bytes()).hexdigest()!=dr['weights_sha256'] or dr['model_sha256']!=corpus['model_sha256']:raise ValueError('decoder provenance')
    with np.load(a.decoder) as f:decoder={k:f[k] for k in f.files}
    pick=np.flatnonzero(decoder['alphas']==dr['selected']['partition'])
    if len(pick)!=1:raise ValueError('decoder selection')
    decoder['selected_coef']=decoder['coef'][:,pick]
    data={};seen=set();templates=set()
    for split in ('train','validation'):
        parts=[];rows=[];offset=0
        for r in corpus['records']:
            if r['partition']!=split:continue
            if r['case'] in seen:raise ValueError('program leakage')
            seen.add(r['case'])
            metadata=json.loads(Path(r['capture']).with_suffix('.json').read_text())
            templates.add(json.dumps(metadata['recipe']['rules'][0],sort_keys=True))
            x,e,y,rr=load(r);parts.append((x,e,y))
            rows.extend(dict(v,index=v['index']+offset) for v in rr);offset+=len(x)
        if not parts:raise ValueError('empty partition')
        data[split]=(*(np.concatenate([p[j] for p in parts]) for j in range(3)),rows)
    if len(templates)!=1:raise ValueError('mixed Cell templates require separate adapters')
    tx,te,ty,_=data['train'];vx,ve,vy,vr=data['validation'];base=np.tanh(vx@resident)
    reports={'resident':dict(eq=eq_audit(vr,base,decoder),rmse=float(np.sqrt(np.mean((base-vy)**2))))};weights={}
    residual=np.arctanh(np.clip(ty,-.999,.999))-tx@resident
    for label,train_x,val_x in [('base_inputs',tx,vx),('with_relations',np.concatenate([tx,te],1),np.concatenate([vx,ve],1))]:
        reports[label]={}
        for alpha in (1.,10.,100.):
            coef,bias=fit(train_x,residual,alpha)
            pred=np.tanh(vx@resident+val_x@coef+bias)
            gpu=mx.tanh(mx.array(vx)@mx.array(resident)+mx.array(val_x)@mx.array(coef)+mx.array(bias));mx.eval(gpu)
            reports[label][str(alpha)]=dict(eq=eq_audit(vr,pred,decoder),rmse=float(np.sqrt(np.mean((pred-vy)**2))),gpu_max_abs=float(np.max(abs(np.array(gpu)-pred))))
            weights[label+'_'+str(alpha)+'_coef']=coef;weights[label+'_'+str(alpha)+'_bias']=bias
    np.savez_compressed(a.weights,parent_model_sha256=corpus['model_sha256'],rule_json=next(iter(templates)),**weights)
    nearest=np.array([np.min(np.max(abs(tx-x),axis=1)) for x in vx])
    unique_inputs=len(np.unique(tx,axis=0))
    same=0.
    for i,x in enumerate(vx):
        equal=np.all(tx==x,axis=1)
        if equal.any():same=max(same,float(np.max(abs(ty[equal]-vy[i]))))
    result=dict(scope='small real union-family program-separated residual ridge ablation; not autonomous learned execution',backpropagation=False,installed=False,
        corpus_sha256=hashlib.sha256(a.corpus.read_bytes()).hexdigest(),model_sha256=corpus['model_sha256'],decoder_sha256=dr['weights_sha256'],
        training_samples=len(tx),distinct_training_inputs=unique_inputs,validation_samples=len(vx),same_input_target_max_abs=same,validation_near_training_inputs=int(np.count_nonzero(nearest<1e-5)),validation_nearest_input_max_abs=nearest.tolist(),extra_f32_columns=te.shape[1],reports=reports,
        weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),limitations=['Only context rule 283 and short programs','Validation is model selection, not held-out test','Frozen resident source tokens; no generated-token rollout measured','Corrected inference costs extra dense readout; no runtime speedup claim'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
