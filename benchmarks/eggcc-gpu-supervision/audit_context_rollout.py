"""Separate one-step contextual fit from recursive rollout under a frozen decoder."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from audit_training_expansion import verified,summarize
from multi_entry_ridge import arrays,pooling,features,metric
from token_eq_readout import examples,readout_rows,materialize
from packed_cell_replay import executor,prepare
from select_eq_readout import gpu_read


def main():
    p=argparse.ArgumentParser()
    for name in ('trace','model','model_report','readout','readout_report','output'):p.add_argument(name,type=Path)
    a=p.parse_args();report=json.loads(a.model_report.read_text());dr=json.loads(a.readout_report.read_text())
    model=verified(a.model,report,'model_sha256');decoder=verified(a.readout,dr,'weights_sha256')
    raw=read_bytes(a.trace);sha=hashlib.sha256(raw).hexdigest()
    if sha!=report['provenance']['test_trace'] or sha!=dr['test_trace_sha256'] or dr['model_sha256']!=report['model_sha256']:raise ValueError('provenance mismatch')
    # Use the prior validation-selected MSE policy; never select on this audit.
    alpha=dr['selected']['mse'];index=list(decoder['alphas']).index(alpha);coef=decoder['coef'][:,index:index+1]
    nodes,rows=examples(json.loads(raw),int(model['channels']),bool(model['zero_role_channels']),True,str(model['encoding']))
    seed,q,target=arrays(nodes);valid=np.array([n['valid'] for n in nodes]);pool=pooling(nodes,target)
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu)
    def one_step(context,weights):
        value=mx.tanh(features(mx.array(seed),mx.array(q),mx.array(context),mx.array(model['w']),mx)@mx.array(weights));mx.eval(value);return np.array(value)
    tokens=dict(oracle_state=target,oracle_providers=one_step(pool,model['coef']),
        predicted_providers=np.array(executor(nodes,model['w'],model['coef'],prepare(nodes,'two'),True)()),
        no_provider_refit=one_step(np.zeros_like(pool),model['zero_provider_coef']))
    results={}
    for name,state in tokens.items():
        matrix,_=materialize(readout_rows(rows,True),state,decoder['w'],True);scores,numeric=gpu_read(matrix,coef)
        results[name]=dict(token_error=metric(state,target,valid),eq=summarize(rows,scores[:,0]),numeric=numeric)
    out=dict(scope='frozen validation-selected decoder, diagnostic oracle-context interventions',model_sha256=report['model_sha256'],
        readout_sha256=dr['weights_sha256'],test_trace_sha256=sha,encoding=str(model['encoding']),alpha=alpha,results=results,
        fitting=False,union_authorized=False,limitations=['Oracle provider/state modes are diagnostics, not executable GPU inputs',
            'No-provider control was fitted previously; this script adds no fit',
            'Eq-only boundary audit does not certify scalar results or graph semantics',
            'No policy or threshold is selected from these test results'])
    a.output.write_text(json.dumps(out,indent=2)+'\n')

if __name__=='__main__':main()
