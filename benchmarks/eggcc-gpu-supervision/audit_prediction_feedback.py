"""Verify nonvacuous predicted-source consumption with unchanged symbolic work."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np


def checked(path):
    meta=json.loads(path.with_suffix('.json').read_text())
    if not meta['capture']['passed'] or hashlib.sha256(path.read_bytes()).hexdigest()!=meta['capture']['artifact_sha256']:raise ValueError('capture provenance')
    return meta


def main():
    p=argparse.ArgumentParser()
    for k in ('exact_sources','predicted_sources','output'):p.add_argument(k,type=Path)
    a=p.parse_args();left=checked(a.exact_sources);right=checked(a.predicted_sources)
    for k in ('recipe','original_recipe','source_rules','model_sha256','trace_sha256','snapshot_run','semantic_recipe'):
        if left[k]!=right[k]:raise ValueError('incompatible comparison: '+k)
    modes=('predicted generated Cells, exact imported Cells','whole-state reconstructed generated Cells, exact imported Cells')
    if left.get('source_token_mode','exact completed states')!='exact completed states' or right['source_token_mode'] not in modes:raise ValueError('feedback mode mismatch')
    reconstructed=right['source_token_mode']==modes[1]
    if reconstructed and not right.get('completion_readout'):raise ValueError('missing completion readout provenance')
    with np.load(a.exact_sources) as x,np.load(a.predicted_sources) as y:
        shared=set(x.files)&set(y.files);symbolic=0
        for key in shared:
            if x[key].dtype.kind in 'biu':
                np.testing.assert_array_equal(x[key],y[key],err_msg=key);symbolic+=1
        np.testing.assert_array_equal(x['targets'],y['targets'])
        feature_delta=np.max(abs(x['features']-y['features']),axis=1)
        token_delta=np.max(abs(x['predicted_tokens']-y['predicted_tokens']),axis=1)
        changed=feature_delta>1e-6;generated=y['generated_source']
        if not generated.any() or not np.any(changed[generated]):raise ValueError('generated-source feedback was not observed')
        # A correctly reconstructed whole state may equal its exact source token.
        # Preserve the stronger original diagnostic for unprojected predictions.
        if not reconstructed and not np.all(changed[generated]):raise ValueError('generated-source feedback was not observed for every consumer')
        source_keys=[k for k in shared if k.endswith('/source_tokens')]
        source_delta=max(float(np.max(abs(x[k]-y[k]))) for k in source_keys)
        if source_delta<=1e-6:raise ValueError('source tokens did not change')
        result=dict(scope='one real selected-family predicted-source feedback comparison; exact matching and effects retained',passed=True,
            exact_capture_sha256=left['capture']['artifact_sha256'],feedback_capture_sha256=right['capture']['artifact_sha256'],model_sha256=left['model_sha256'],
            identical_symbolic_arrays=symbolic,instances=len(generated),generated_source_consumers=int(generated.sum()),
            changed_inputs=int(changed.sum()),changed_generated_inputs=int(np.count_nonzero(changed&generated)),changed_direct_inputs=int(np.count_nonzero(changed&~generated)),
            maximum_source_token_change=source_delta,maximum_feature_change=float(feature_delta.max()),maximum_predicted_token_change=float(token_delta.max()),
            same_cpu_targets=True,backpropagation=False,source_token_mode=right['source_token_mode'],completion_readout=right.get('completion_readout'),
            limitations=['Symbolic equality here is capture comparison; full Run graphs are checked separately by execution audit','Same accuracy does not mean identical scores','Imported Cells still use exact encoding; generated Cells retain birth predictions rather than refreshing learned state after every union','No learned Eq is authorized by this experiment'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
