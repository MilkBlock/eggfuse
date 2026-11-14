"""Separate encoder reconstruction error from score-kernel error on saved GPU captures."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from audit_input_relations import restore
from audit_snapshot_queries import device
from device_match_capture import floating_inputs
from device_completion_classifier import load_head,score_head


def main():
    p=argparse.ArgumentParser()
    for key in ('capture','model','head','output'):p.add_argument(key,type=Path)
    a=p.parse_args();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    meta=json.loads(a.capture.with_suffix('.json').read_text())
    if sha(a.capture)!=meta['capture']['artifact_sha256'] or sha(a.model)!=meta['model_sha256'] or sha(a.head)!=meta['completion_readout']['head_sha256']:raise ValueError('capture/model/head provenance')
    with np.load(a.model) as f:model=dict(w=f['w'])
    with np.load(a.head) as f:heads=dict(f)
    results=[]
    with np.load(a.capture) as f:
        prefixes=[k[:-4] for k in f.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k]
        prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
        for prefix in prefixes:
            c=restore(f,prefix);live=c['bindings']['live']
            if not bool(c['recorded']) or not live.any():continue
            head=load_head(heads,int(c['rule']));dc,dm,dh=map(device,(c,model,head))
            x=floating_inputs(c,model,np);precise=floating_inputs(c,model,np,reference=True)
            gx=mx.compile(lambda v:floating_inputs(v,dm,mx))(dc)
            gs=mx.compile(lambda v:score_head(v,dh,mx))(gx);mx.eval(gx,gs)
            gpu_x=np.array(gx);gpu_score=np.array(gs);record=c['completion_readout']['scores']
            ref=score_head(x,head,np);corrected=score_head(precise,head,np);same=score_head(gpu_x,head,np)
            pairs=dict(features=(x,gpu_x),gpu_replay=(gpu_score,record),same_input_score=(gpu_score,same),encoding_contribution=(same,ref),legacy_reference=(ref,record),precise_reference=(corrected,record))
            errors={k:float(np.max(abs(left[live]-right[live]))) for k,(left,right) in pairs.items()}
            results.append(dict(prefix=prefix,rule=meta['source_rules'][int(c['rule'])],lanes=int(live.sum()),maximum_errors=errors))
    if not results:raise ValueError('no recorded live lanes')
    maxima={k:max(r['maximum_errors'][k] for r in results) for k in results[0]['maximum_errors']}
    a.output.write_text(json.dumps(dict(scope='saved GPU numeric replay only; not semantic acceptance or speed',capture_sha256=sha(a.capture),head_sha256=sha(a.head),maxima=maxima,results=results),indent=2)+'\n')
    print(json.dumps(maxima))

if __name__=='__main__':main()
