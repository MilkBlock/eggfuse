"""Separate token readout, direct completion and recurrent errors; no fitting."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from multi_entry_ridge import arrays,pooling,features
from token_eq_readout import examples,readout_rows,materialize,expand_scores
from packed_cell_replay import executor,prepare
from select_eq_readout import gpu_read
from audit_training_expansion import summarize


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(trace_path,model_path,model_report,weights_path,selection_report):
    mr=json.loads(model_report.read_text());sr=json.loads(selection_report.read_text())
    if digest(model_path)!=mr['model_sha256'] or mr['model_sha256']!=sr['model_sha256']:raise ValueError('model provenance mismatch')
    if digest(weights_path)!=sr['weights_sha256']:raise ValueError('readout provenance mismatch')
    raw=read_bytes(trace_path)
    if hashlib.sha256(raw).hexdigest()!=sr['test_trace_sha256'] or sr['test_trace_sha256']!=mr['provenance']['test_trace']:raise ValueError('trace provenance mismatch')
    with np.load(model_path) as f:model={k:f[k] for k in f.files}
    with np.load(weights_path) as f:decoder={k:f[k] for k in f.files}
    nodes,rows=examples(json.loads(raw),int(model['channels']),bool(model['zero_role_channels']),True,str(model['encoding']),bool(model.get('source_neighborhood',False)),bool(model.get('source_relations',False)))
    seed,q,target=arrays(nodes);pool=pooling(nodes,target)
    direct=mx.tanh(features(mx.array(seed),mx.array(q),mx.array(pool),mx.array(model['w']),mx)@mx.array(model['coef']));mx.eval(direct)
    rollout=np.array(executor(nodes,model['w'],model['coef'],prepare(nodes,'two'),True)())
    alpha=sr['selected']['partition'];ids=np.flatnonzero(decoder['alphas']==alpha)
    if len(ids)!=1:raise ValueError('missing selected decoder')
    coef=decoder['coef'][:,ids];results={};errors={}
    for mode,tokens in [('oracle_state',target),('direct_gold_sources',np.array(direct)),('rollout',rollout)]:
        matrix,_=materialize(readout_rows(rows,True),tokens,decoder['w'],True)
        score,numeric=gpu_read(matrix,coef);score=score[:,0]
        results[mode]=dict(summarize(rows,score),numerical_audit=numeric)
        wrong=set();offset=0
        for i,row in enumerate(rows):
            size=len(row['quotient']['representatives'])
            full=expand_scores(row,score[offset:offset+size],True,True);offset+=size
            if len(row['pairs']) and not np.array_equal(full>=.5,row['y']):wrong.add(i)
        errors[mode]=wrong
    oracle=errors['oracle_state'];direct=errors['direct_gold_sources'];roll=errors['rollout']
    return dict(scope='held-out observed-wiring diagnostic; frozen token model and decoder; not runtime correctness',
                model_sha256=mr['model_sha256'],trace_sha256=sr['test_trace_sha256'],weights_sha256=sr['weights_sha256'],alpha=float(alpha),
                reports=results,error_overlap=dict(oracle_wrong=len(oracle),direct_wrong=len(direct),rollout_wrong=len(roll),
                direct_wrong_with_oracle_correct=len(direct-oracle),rollout_wrong_with_direct_correct=len(roll-direct),
                direct_wrong_but_rollout_correct=len(direct-roll)),backpropagation=False,
                limitations=['Correct source tokens and completed states are audit-only labels',
                'Overlap is not a causal decomposition: prediction errors may cancel decoder errors',
                'No token model or readout policy is selected using this test diagnostic'])


def main():
    p=argparse.ArgumentParser()
    for name in ('trace','model','model_report','weights','selection_report','output'):p.add_argument(name,type=Path)
    a=p.parse_args();result=audit(a.trace,a.model,a.model_report,a.weights,a.selection_report)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
