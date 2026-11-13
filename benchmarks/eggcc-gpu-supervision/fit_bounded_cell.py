"""Fit an absolute bounded Cell state with a closed-form ridge solve."""
import argparse,gzip,hashlib,json
from pathlib import Path
import numpy as np
from corpus_cell_ridge import load_records,features,initial_attachment
from boundary_cell_ridge import D,state,output_layout,request_with_roles
from bake_stop_features import plan,pack,evaluate
from whole_cell_ridge import train
from corpus_repeat_probe import state_bound,bound_state,wiring as input_wiring
from bounded_cell_readout import readout_features,preactivation,normalize,port_moments


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('base',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path);p.add_argument('--readout',choices=['tanh','clip'],default='tanh');p.add_argument('--extra-features',type=int,default=0);p.add_argument('--port-moments',action='store_true');a=p.parse_args()
    if not 0<=a.extra_features<=2048:raise ValueError('extra feature count outside experiment bounds')
    meta=json.loads(gzip.decompress(a.base.with_suffix('.json.gz').read_bytes()));mh=hashlib.sha256(a.manifest.read_bytes()).hexdigest()
    if meta['manifest_sha256']!=mh:raise ValueError('manifest mismatch')
    if not meta.get('positioned_roles'):raise ValueError('positional role model required')
    records,_=load_records(json.loads(a.manifest.read_text()));records=[r for r in records if r['split']!='test']
    with np.load(a.base) as z:weights={k:z[k] for k in z.files}
    if 'stop_coef' not in weights:raise ValueError('independent stop head required')
    if 'correction_coef' in weights or 'direct_coef' in weights:raise ValueError('base must use the original residual readout')
    direct_w=weights['w']
    if a.extra_features:
        extra=np.random.default_rng(120).normal(0,1/16,(direct_w.shape[0],a.extra_features)).astype(np.float32)
        direct_w=np.concatenate([direct_w,extra],axis=1)
    weights['direct_w']=direct_w
    xs=[];ys=[];splits=[]
    for i,r in enumerate(records):
        s=r['sample'];done=s['completion'];ports,mapping,_=output_layout(s['source'],done)
        initial=state(s['source'],ports,meta['capacity'],allow_absent=True).astype(np.float32);target=state(done['facts'],ports,meta['capacity'],mapping).astype(np.float32)
        q=request_with_roles(r['rule'],s['binding'],False)[None,:];role=request_with_roles(r['rule'],s['binding'],True)[None,:]
        bounds=np.array([state_bound(s['source'],r['rule'])],np.float32)
        input_indices,input_mix=input_wiring(ports,s['binding'],max(1,len(s['binding'])))
        wiring=pack([plan(s['source'],r['rule'],s['binding'],ports,meta['capacity'])])
        def encode(v):
            att=initial_attachment(v,ports,s['binding'])[None,:]
            basic=features(v[None,:],q,att,weights['w'],np,role)
            return basic,np.concatenate([basic,evaluate(v[None,:],*wiring,np)],axis=1)
        basic,_=encode(initial);candidate=initial+(basic@weights['coef'])[0,:-1]
        candidate=bound_state(candidate[None,:],bounds,np)[0]
        label=preactivation(target[None,:],bounds)[0]
        if a.readout=='clip':label=normalize(target[None,:],bounds,np)[0]
        for value in (initial,candidate,target):
            att=initial_attachment(value,ports,s['binding'])[None,:]
            moments=port_moments(value[None,:],input_indices[None,:],input_mix[None,:],np) if a.port_moments else None
            x=readout_features(value[None,:],q,att,direct_w,role,bounds,wiring,np,moments)
            xs.append(x[0]);ys.append(label);splits.append(r['split'])
        if i%250==0:print(json.dumps(dict(encoded=i,total=len(records))),flush=True)
    x=np.array(xs,np.float32);y=np.array(ys,np.float32);splits=np.array(splits)
    scale=np.concatenate([np.full(D,1/np.sqrt(D)),np.full(y.shape[1]-D,1/np.sqrt(y.shape[1]-D))]).astype(np.float32)
    coef,fit=train(x,y*scale,splits=='train',splits=='validation');weights['direct_coef']=coef/scale[None,:]
    reconstruction={}
    for part in ('train','validation'):
        reconstruction[part]={}
        for offset,name in enumerate(('initial','predicted','completed')):
            mask=(splits==part)&(np.arange(len(x))%3==offset);pred=x[mask]@weights['direct_coef']
            decoded=np.tanh(pred) if a.readout=='tanh' else np.clip(pred,-1,1)
            truth=np.tanh(y[mask]) if a.readout=='tanh' else y[mask]
            reconstruction[part][name]=dict(cases=int(mask.sum()),normalized_body_rmse=float(np.sqrt(np.mean((decoded[:,:D]-truth[:,:D])**2))),boundary_rmse=float(np.sqrt(np.mean((decoded[:,D:]-truth[:,D:])**2))))
    with a.model.open('wb') as f:np.savez_compressed(f,**weights)
    meta['port_moments']=a.port_moments
    meta['direct_readout']='normalized absolute '+a.readout+' state/v1';meta['direct_mode']=a.readout;meta['direct_base_sha256']=hashlib.sha256(a.base.read_bytes()).hexdigest()
    a.model.with_suffix('.json.gz').write_bytes(gzip.compress(json.dumps(meta).encode(),mtime=0))
    result=dict(scope='standalone absolute bounded state; no test fitting, no backpropagation',manifest_sha256=mh,model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),base_sha256=meta['direct_base_sha256'],fit=fit,port_moments=a.port_moments,extra_features=a.extra_features,feature_width=x.shape[1],reconstruction=reconstruction,readout=a.readout,training_rows=int((splits=='train').sum()),validation_rows=int((splits=='validation').sum()),test_rows=0)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)

if __name__=='__main__':main()
