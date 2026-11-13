"""Compare frozen token models under observed single-witness input selection."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from source_moment_probe import load
from source_witness_probe import choose,inputs,eq_rows,eq_audit
from multi_entry_ridge import arrays,metric,replay


def main():
    p=argparse.ArgumentParser()
    p.add_argument('validation',type=Path);p.add_argument('decoder',type=Path);p.add_argument('decoder_report',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--model',nargs=3,action='append',required=True,metavar=('NAME','WEIGHTS','REPORT'))
    a=p.parse_args();started=time.monotonic()
    manifest_sha=hashlib.sha256(a.validation.read_bytes()).hexdigest()
    nodes,manifest=load(a.validation)
    if manifest['partition']!='validation':raise ValueError('validation only')
    rows,count=eq_rows(a.validation)
    if count!=len(nodes):raise ValueError('row alignment')
    dr=json.loads(a.decoder_report.read_text());decoder_sha=hashlib.sha256(a.decoder.read_bytes()).hexdigest()
    if decoder_sha!=dr['weights_sha256'] or dr['provenance']['validation']!=manifest_sha:raise ValueError('decoder provenance')
    with np.load(a.decoder) as f:decoder={k:f[k] for k in f.files}
    indices=np.flatnonzero(decoder['alphas']==dr['selected']['partition'])
    if len(indices)!=1:raise ValueError('decoder selection')
    decoder['selected_coef']=decoder['coef'][:,indices]
    target=arrays(nodes)[2];valid=np.array([n['valid'] for n in nodes]);results={};provenance={}
    views=dict(all=nodes,first=choose(nodes,'first'),last=choose(nodes,'last'))
    for name,weights,report in a.model:
        if name in results:raise ValueError('duplicate model name')
        raw=Path(weights).read_bytes();mr=json.loads(Path(report).read_text());sha=hashlib.sha256(raw).hexdigest()
        if sha!=mr['model_sha256']:raise ValueError('model provenance')
        train_sha=mr.get('training_manifest_sha256',mr.get('provenance',{}).get('train'))
        if train_sha!=dr['provenance']['train']:raise ValueError('training provenance mismatch')
        with np.load(weights) as f:model={k:f[k] for k in f.files}
        if int(model['channels'])!=4 or str(model['encoding'])!='class-history-neighborhood-input' or bool(model['zero_role_channels']) or bool(model.get('source_neighborhood',False)) or bool(model.get('source_relations',False)):raise ValueError('incompatible input encoding')
        provenance[name]=dict(model_sha256=sha,training_manifest_sha256=train_sha,
            fit_validation_sha256=mr.get('validation_manifest_sha256',mr.get('provenance',{}).get('validation')))
        result={}
        for policy,view in views.items():
            x=inputs(view,target,model['w']);direct=mx.tanh(mx.array(x)@mx.array(model['coef']));mx.eval(direct)
            direct=np.array(direct);rolled=replay(view,model['w'],model['coef'],True)
            audit_start=time.monotonic()
            exact_direct=eq_audit(rows,direct,decoder);exact_roll=eq_audit(rows,rolled,decoder)
            result[policy]=dict(direct=metric(direct,target,valid),rollout=metric(rolled,target,valid),
                eq_direct=exact_direct,eq_rollout=exact_roll,cpu_eq_audit_seconds=time.monotonic()-audit_start)
        results[name]=result
        print(name+' audited',flush=True)
    out=dict(scope='frozen-model observed-wiring validation comparison; not full runtime acceptance',
        validation_manifest_sha256=manifest_sha,decoder_sha256=decoder_sha,provenance=provenance,results=results,
        refitting=False,backpropagation=False,union_authorized=False,seconds=time.monotonic()-started,
        limitations=['Source observations lack full visibility/generation proof','Single-port choices may not form one jointly realizable query witness',
            'Validation comparison, not held-out test accuracy','CPU Eq audit timing includes feature materialization and partition checks only'])
    a.output.write_text(json.dumps(out,indent=2)+'\n')

if __name__=='__main__':main()
