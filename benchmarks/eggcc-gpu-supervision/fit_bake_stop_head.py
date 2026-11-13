"""Fit only the emission head; preserve the saved whole-state readout exactly."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from corpus_cell_ridge import load_records,features,initial_attachment
from boundary_cell_ridge import D,state,output_layout,request_with_roles
from whole_cell_ridge import train
from dominator_completion import compose,freeze
from bake_stop_features import plan,pack,evaluate,NAMES


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('base_model',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path);p.add_argument('--no-bake-hints',action='store_true');args=p.parse_args()
    metadata=json.loads(gzip.decompress(args.base_model.with_suffix('.json.gz').read_bytes()));manifest_hash=hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    if metadata['manifest_sha256']!=manifest_hash:raise ValueError('manifest mismatch')
    records,_=load_records(json.loads(args.manifest.read_text()))
    with np.load(args.base_model) as z:weights={k:z[k] for k in z.files}
    w=weights['w'];capacity=metadata['capacity'];xs=[];ys=[];splits=[];kinds=[]
    for i,r in enumerate(records):
        sample=r['sample'];done=sample['completion'];ports,mapping,_=output_layout(sample['source'],done)
        original=state(sample['source'],ports,capacity,allow_absent=True);completed=state(done['facts'],ports,capacity,mapping)
        quotient={freeze(a):freeze(b) for a,b in done['source_map']}
        repeated,reason=compose(done['facts'],r['rule'],[(slot,quotient[freeze(v)]) for slot,v in sample['binding']],r['tables'])
        if reason or repeated['novel']:raise ValueError('unproved completed-state label')
        q=request_with_roles(r['rule'],sample['binding'],False)[None,:]
        role=request_with_roles(r['rule'],sample['binding'],metadata['positioned_roles'])[None,:] if metadata['positioned_roles'] else np.zeros((1,D),np.float32)
        wiring=pack([plan(sample['source'],r['rule'],sample['binding'],ports,capacity)])
        for kind,s,label in [('initial',original,done['novel']),('completed',completed,False),('identity',original,False)]:
            query=q if kind!='identity' else np.zeros_like(q);roles=role if kind!='identity' else np.zeros_like(role)
            a=initial_attachment(s,ports,sample['binding'])[None,:] if kind!='identity' else np.zeros((1,D),np.float32)
            basic=features(s[None,:],query,a,w,np,roles)
            extra=evaluate(s[None,:],*wiring,np) if kind!='identity' and not args.no_bake_hints else np.zeros((1,len(NAMES)),np.float32)
            xs.append(np.concatenate([basic,extra],axis=1)[0]);ys.append(label);splits.append(r['split']);kinds.append(kind)
        if i%250==0:print(json.dumps(dict(encoded=i,total=len(records))),flush=True)
    x=np.array(xs,np.float32);y=np.array(ys,np.float32);split=np.array(splits);kind=np.array(kinds)
    coef,fit=train(x,y[:,None],split=='train',split=='validation');score=(x@coef)[:,0];emit=score>=.5
    reports={}
    for part in ('train','validation','test'):
        reports[part]={}
        for category in ('initial','completed','identity'):
            mask=(split==part)&(kind==category)
            reports[part][category]=dict(cases=int(mask.sum()),positive=int(y[mask].sum()),false_emissions=int((mask&emit&~y.astype(bool)).sum()),missed_emissions=int((mask&~emit&y.astype(bool)).sum()))
    weights['stop_coef']=coef
    args.model.parent.mkdir(parents=True,exist_ok=True)
    with args.model.open('wb') as output:np.savez_compressed(output,**weights)
    metadata.update(stop_hints_active=not args.no_bake_hints,stop_feature_version='output-energy-direct-union/v1',stop_feature_names=NAMES,stop_head_base_sha256=hashlib.sha256(args.base_model.read_bytes()).hexdigest())
    args.model.with_suffix('.json.gz').write_bytes(gzip.compress(json.dumps(metadata).encode(),mtime=0))
    result=dict(scope='head-only ridge fit with static Bake hints; state predictor unchanged',manifest_sha256=manifest_hash,base_model_sha256=metadata['stop_head_base_sha256'],model=str(args.model),model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),fit=fit,stop_hints_active=not args.no_bake_hints,backpropagation=False,features=NAMES,reports=reports,limitations=['Output layout comes from the supported finite Bake catalog','Feature energy is not an equality or existence proof','Repeated free GPU inference must be evaluated separately','No full ruleset, source-stage or ownership guarantee'])
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
