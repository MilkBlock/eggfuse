"""Audit differentiable third-step replay, with exact-input overlap separated."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np
import mlx.core as mx
from neural_third_step import replay,replay_blocks,fingerprints
from train_neural_eq_readout import CompletionReadout
from neural_eq_readout import metrics


def main():
    p=argparse.ArgumentParser();p.add_argument('data',type=Path);p.add_argument('weights',type=Path);p.add_argument('output',type=Path);p.add_argument('--training-data',type=Path);p.add_argument('--without-context',action='store_true');p.add_argument('--block-owner',action='store_true');p.add_argument('--without-source-update',action='store_true');p.add_argument('--case-limit',type=int);a=p.parse_args()
    if a.without_source_update and not a.block_owner:raise ValueError('source update ablation requires block model')
    data=dict(np.load(a.data,allow_pickle=False))
    if a.case_limit is not None:
        if a.case_limit<1:raise ValueError('positive case limit required')
        keep=data['case']<a.case_limit;data={k:v[keep] for k,v in data.items()}
        if not len(data['valid']):raise ValueError('empty case selection')
    original=data
    if a.block_owner!=('c_owner_request' in data):raise ValueError('model and replay ownership layout differ')
    if a.without_context:
        mask=data['mask'].copy();mask[:,data['p_x'].shape[1]:]=False;data=dict(data,mask=mask)
    width=(1+math.isqrt(1+8*data['eq_target'].shape[1]))//2
    if width*(width-1)//2!=data['eq_target'].shape[1]:raise ValueError('invalid equality output layout')
    if a.block_owner:
        from neural_owner_blocks import OwnerBlocks
        model=OwnerBlocks(data['p_x'].shape[-1],data['relations'].shape[-1],width)
    else:model=CompletionReadout(data['p_x'].shape[-1],data['relations'].shape[-1],width)
    model.load_weights(str(a.weights))
    if a.without_source_update:
        model.update_source.layers[-1].weight=mx.zeros_like(model.update_source.layers[-1].weight)
        model.update_source.layers[-1].bias=mx.zeros_like(model.update_source.layers[-1].bias)
    out=[];matches=[];finite=[]
    for start in range(0,len(data['valid']),128):
        b={k:mx.array(v[start:start+128]) for k,v in data.items()};logit,token=replay_blocks(model,b) if a.block_owner else replay(model.cell,b)
        score=model.eq(token,b['request']);mx.eval(logit,score)
        out.append(np.array(score));matches.append(np.array(logit)>=0);finite.append(np.isfinite(np.array(logit)))
    score=np.concatenate(out);pos=data['valid']>0
    report=dict(scope='standalone synthetic three-step floating replay with fixed exact routing; no graph mutations',
        case_limit=a.case_limit,block_owner=a.block_owner,source_update_disabled=a.without_source_update,context_masked=a.without_context,eq=metrics(score[pos],data['eq_target'][pos],data['eq_mask'][pos],width),matching_errors=int((np.concatenate(matches)!=pos).sum()),nonfinite_matches=int((~np.concatenate(finite)).sum()),weights_sha256=hashlib.sha256(a.weights.read_bytes()).hexdigest(),dataset_sha256=hashlib.sha256(a.data.read_bytes()).hexdigest())
    if a.training_data:
        train=dict(np.load(a.training_data,allow_pickle=False));seen=set(fingerprints(train));overlap=np.array([v in seen for v in fingerprints(original)]);novel=pos&~overlap
        report.update(overlapping_candidates=int(overlap.sum()),overlapping_positive_states=int((overlap&pos).sum()),unseen_positive=metrics(score[novel],data['eq_target'][novel],data['eq_mask'][novel],width),training_sha256=hashlib.sha256(a.training_data.read_bytes()).hexdigest())
    passed=report['eq']['closed_exact_states']==int(pos.sum()) and not report['matching_errors'] and not report['nonfinite_matches'] and bool(pos.any())
    report['status']='pass' if passed else 'difference';a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
