"""Exact f32 feature conflicts for the bounded readout; diagnostic only."""
import argparse,gzip,hashlib,json
from collections import defaultdict
from pathlib import Path
import numpy as np
from corpus_cell_ridge import load_records,initial_attachment
from boundary_cell_ridge import state,output_layout,request_with_roles
from corpus_repeat_probe import state_bound
from bounded_cell_readout import readout_features,normalize
from bake_stop_features import plan,pack


def fingerprint(values):return hashlib.sha256(np.asarray(values,np.float32).tobytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    mh=hashlib.sha256(a.manifest.read_bytes()).hexdigest();meta=json.loads(gzip.decompress(a.model.with_suffix('.json.gz').read_bytes()))
    if meta['manifest_sha256']!=mh or not meta['positioned_roles']:raise ValueError('model contract mismatch')
    with np.load(a.model) as z:w=z['direct_w'] if 'direct_w' in z.files else z['w']
    records,_=load_records(json.loads(a.manifest.read_text()));groups=defaultdict(list)
    for r in records:
        if r['split']=='validation':continue
        s=r['sample'];ports,mapping,_=output_layout(s['source'],s['completion']);cap=meta['capacity']
        v=state(s['source'],ports,cap,allow_absent=True).astype(np.float32);target=state(s['completion']['facts'],ports,cap,mapping).astype(np.float32)
        bounds=np.array([state_bound(s['source'],r['rule'])],np.float32);q=request_with_roles(r['rule'],s['binding'],False)[None,:];role=request_with_roles(r['rule'],s['binding'],True)[None,:];att=initial_attachment(v,ports,s['binding'])[None,:]
        wiring=pack([plan(s['source'],r['rule'],s['binding'],ports,cap)])
        x=readout_features(v[None,:],q,att,w,role,bounds,wiring,np).astype(np.float32)
        groups[fingerprint(x)].append(dict(identity=r['identity'],split=r['split'],family=r['family'],target_digest=fingerprint(normalize(target[None,:],bounds,np))))
    conflicts=[dict(feature_digest=k,inputs=rows) for k,rows in groups.items() if len({r['target_digest'] for r in rows})>1]
    result=dict(scope='exact f32 initial-feature collisions only; no near-collision or recurrent-state proof',manifest_sha256=mh,model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),feature_groups=len(groups),conflicting_groups=len(conflicts),conflicts=conflicts)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='conflicts'}))

if __name__=='__main__':main()
