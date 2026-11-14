"""Recover a baked finite Eq state from its floating token and actual scalars.

Diagnostic only: no head choices/labels enter decoding. Not proof of completion,
not an unbounded decoder, and not a replacement for runtime inference.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from audit_input_relations import restore
from audit_snapshot_queries import device
from device_completion_readout import compile_state_layout
from device_completion_states import tokens


def recover(value,codes,plan,xp):
    n=len(value);k=len(plan['states']);s=codes.shape[1]
    indexes=xp.broadcast_to(xp.arange(k)[None,:],(n,k)).reshape(-1)
    scalar=xp.broadcast_to(codes[:,None,:,:],(n,k,s,64)).reshape(n*k,s,64)
    candidates=tokens(indexes,scalar,plan['token'],xp).reshape(n,k,128)
    distances=xp.sum((value[:,None,:]-candidates)**2,axis=-1)
    chosen=xp.argmin(distances,axis=1)
    # Distinguish a nearest guess from an actual reconstruction with a margin.
    best=xp.min(distances,axis=1)
    other=xp.where(xp.arange(k)[None,:]==chosen[:,None],float('inf'),distances)
    return chosen,best,xp.min(other,axis=1)-best


def main():
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    meta=json.loads(a.capture.with_suffix('.json').read_text())
    if not meta['capture']['passed'] or hashlib.sha256(a.capture.read_bytes()).hexdigest()!=meta['capture']['artifact_sha256']:raise ValueError('capture provenance')
    rows=[];recovered=[]
    with np.load(a.capture) as data:
        prefixes=[k[:-4] for k in data.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k]
        prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
        for prefix in prefixes:
            c=restore(data,prefix);mask=c['accepted']
            if not np.any(mask):continue
            d=c['completion_readout'];rid=int(c['rule']);plan=compile_state_layout(meta['recipe']['rules'][rid])
            values=c['predicted_tokens'][mask];codes=d['scalar_codes'][mask]
            if not np.isfinite(values).all() or not np.isfinite(codes).all():raise ValueError('nonfinite token input')
            got,error,margin=recover(values,codes,plan,np)
            dp=device(plan);g=mx.compile(lambda x,y:recover(x,y,dp,mx))(mx.array(values),mx.array(codes));mx.eval(g)
            np.testing.assert_array_equal(g[0],got)
            np.testing.assert_allclose(g[1],error,atol=1e-9);np.testing.assert_allclose(g[2],margin,atol=1e-6)
            # Compare against producer metadata only after independent recovery.
            expected=d['chosen'][mask]
            recovered.extend(plan['states'][got])
            rows.append(dict(prefix=prefix,rule=rid,instances=len(got),mismatches=int(np.count_nonzero(got!=expected)),
                maximum_squared_error=float(error.max()),minimum_margin=float(margin.min())))
        semantic_result=None
        if 'target_eq_classes' in data:
            from audit_device_match_readout import rows_from_labels,dynamic_metrics
            from audit_training_expansion import summarize
            rr=rows_from_labels(meta['semantic_recipe'],[meta['source_rules'].index(int(r)) for r in data['rules']],data['target_eq_classes'])
            if len(rr)!=len(recovered):raise ValueError('label alignment')
            truth=np.concatenate([r['y'][r['quotient']['representatives']] for r in rr]);scores=np.concatenate(recovered)
            if truth.shape!=scores.shape:raise ValueError('semantic layout mismatch')
            semantic_result=dict(summarize(rr,scores),dynamic_quotient=dynamic_metrics(truth,scores))
    if not rows:raise ValueError('no completed tokens')
    report=dict(scope='finite baked state recoverability audit on actual captured tokens; not semantic correctness',
        instances=sum(r['instances'] for r in rows),mismatches=sum(r['mismatches'] for r in rows),
        maximum_squared_error=max(r['maximum_squared_error'] for r in rows),minimum_margin=min(r['minimum_margin'] for r in rows),
        recovered_state_semantics=semantic_result,capture_sha256=meta['capture']['artifact_sha256'],uses_labels_for_decoding=False,uses_producer_choice_for_decoding=False,backpropagation=False,rows=rows)
    report['passed']=report['mismatches']==0 and report['maximum_squared_error']<1e-9 and report['minimum_margin']>1e-6
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':main()
