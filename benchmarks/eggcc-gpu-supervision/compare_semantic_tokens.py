"""Like-for-like Cell prediction audit across compiler representation changes."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser()
    for k in ('before','after','before_readout','after_readout','output'):p.add_argument(k,type=Path)
    a=p.parse_args();reports=[];metas=[]
    for archive,readout in [(a.before,a.before_readout),(a.after,a.after_readout)]:
        meta=json.loads(archive.with_suffix('.json').read_text());r=json.loads(readout.read_text());sha=hashlib.sha256(archive.read_bytes()).hexdigest()
        if sha!=meta['capture']['artifact_sha256'] or sha!=r['capture_sha256'] or not meta['capture']['passed']:raise ValueError('audit provenance')
        metas.append(meta);reports.append(r)
    if metas[0]['trace_sha256']!=metas[1]['trace_sha256'] or metas[0]['model_sha256']!=metas[1]['model_sha256'] or metas[0]['semantic_recipe']!=metas[1]['semantic_recipe']:raise ValueError('semantic comparison changed source or model')
    if reports[0]['decoder_sha256']!=reports[1]['decoder_sha256']:raise ValueError('decoder changed')
    with np.load(a.before) as before,np.load(a.after) as after:
        if set(before.files)!=set(after.files):raise ValueError('capture schema changed')
        checked=0
        for key in before.files:
            if key.startswith('capture/') and before[key].dtype.kind in 'biu':
                np.testing.assert_array_equal(before[key],after[key]);checked+=1
        for key in ('rules','target_eq_classes','generated_source','targets'):np.testing.assert_array_equal(before[key],after[key])
        samples=len(before['rules'])
    result=dict(scope='same original Cell semantics, same actual witnesses and frozen weights; not a speed measurement',
        before_sha256=reports[0]['capture_sha256'],after_sha256=reports[1]['capture_sha256'],samples=samples,integer_boolean_capture_arrays_equal=checked,
        target_tokens_and_partitions_equal=True,model_weights_unchanged=True,decoder_weights_unchanged=True,
        before=reports[0]['results'],after=reports[1]['results'],before_groups=reports[0]['groups'],after_groups=reports[1]['groups'],
        limitations=['Training program; no new held-out generalization result','Raw compiler-slot baseline uses a different semantic interface and is not this comparison','Exact execution still authorizes completion'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
