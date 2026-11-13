"""Inspect recurrent failures without adding held-out samples to training."""
import argparse,gzip,json,hashlib
from pathlib import Path
import numpy as np
from corpus_cell_ridge import load_records,features,initial_attachment
from boundary_cell_ridge import D,state,output_layout,request_with_roles
from bake_stop_features import plan,pack,evaluate,NAMES


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('model',type=Path);p.add_argument('probe',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    records,_=load_records(json.loads(a.manifest.read_text()));meta=json.loads(gzip.decompress(a.model.with_suffix('.json.gz').read_bytes()))
    probe=json.loads(a.probe.read_text())
    manifest_hash=hashlib.sha256(a.manifest.read_bytes()).hexdigest();model_hash=hashlib.sha256(a.model.read_bytes()).hexdigest()
    if meta['manifest_sha256']!=manifest_hash or probe['manifest_sha256']!=manifest_hash or probe['model_sha256']!=model_hash:raise ValueError('artifact fingerprint mismatch')
    failed={r['input_identity'] for r in probe['failure_diagnostics']}
    training=[r for r in records if r['split']=='train'];rows=[]
    with np.load(a.model) as z:w=z['w'];coef=z['coef'];head=z['stop_coef']
    for r in records:
        if r['split']!='test' or r['identity'] not in failed:continue
        s=r['sample'];done=s['completion'];ports,mapping,new=output_layout(s['source'],done);wiring=pack([plan(s['source'],r['rule'],s['binding'],ports,meta['capacity'])])
        q=request_with_roles(r['rule'],s['binding'],False)[None,:];role=request_with_roles(r['rule'],s['binding'],True)[None,:]
        initial=state(s['source'],ports,meta['capacity'],allow_absent=True).astype(np.float32);oracle=state(done['facts'],ports,meta['capacity'],mapping).astype(np.float32)
        def inspect(v):
            attachment=initial_attachment(v,ports,s['binding'])[None,:];x=features(v[None,:],q,attachment,w,np,role);h=evaluate(v[None,:],*wiring,np)
            return float((np.concatenate([x,h],axis=1)@head)[0,0]),dict(zip(NAMES,h[0].tolist())),x
        score,h,x=inspect(initial);predicted=initial+(x@coef)[0,:-1] if score>=.5 else initial
        os,oh,_=inspect(oracle);ps,ph,_=inspect(predicted)
        rows.append(dict(identity=r['identity'],family=r['family'],training_family_inputs=sum(t['family']==r['family'] for t in training),exact_training_input=any(t['identity']==r['identity'] for t in training),source_facts=len(s['source']),output_ports=len(new),effects=r['rule']['effects'],initial_score=score,oracle_score=os,predicted_once_score=ps,initial_hints=h,oracle_hints=oh,predicted_once_hints=ph,body_rmse_after_one=float(np.sqrt(np.mean((predicted[:D]-oracle[:D])**2)))))
    if len(rows)!=len(failed):raise ValueError('missing failed input')
    result=dict(scope='held-out diagnosis only; no training modification',manifest_sha256=manifest_hash,model_sha256=model_hash,failures=rows)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    for r in rows:print(json.dumps({k:v for k,v in r.items() if k not in ('effects','initial_hints','oracle_hints','predicted_once_hints')}))

if __name__=='__main__':main()
