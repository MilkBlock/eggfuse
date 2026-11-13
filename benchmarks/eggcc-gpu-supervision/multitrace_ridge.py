"""Frozen whole-workload evaluation of alias-normalized floating Cell ridge.

No target labels enter routing/encoding. Roles share typed compiler semantics,
while runtime root groups never cross source Runs or workloads.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import mlx.core as mx
from collect_multitrace import CASES
from context_ridge import prepare, metrics, proposal_packets
from calibrated_ridge import typed_roles, structured_encode, select


def combine(traces):
    merged=dict(recipe=dict(rules=[]),runs=[],steps=[])
    ranges=[];offset=0
    for trace in traces:
        rule_offset=len(merged['recipe']['rules'])
        merged['recipe']['rules'].extend(copy.deepcopy(trace['recipe']['rules']))
        for step in trace['steps']:
            step=copy.deepcopy(step);step['ordinal']+=offset;merged['steps'].append(step)
        for run in trace['runs']:
            run=copy.deepcopy(run);run['ordinal']+=offset
            for b in run['audit']['bindings']:b['rule']+=rule_offset
            merged['runs'].append(run)
        ranges.append((offset,offset+len(trace['steps'])));offset+=len(trace['steps'])
    return merged,ranges


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('output',type=Path);p.add_argument('--proposals',type=Path,required=True);args=p.parse_args()
    manifest=json.loads(args.manifest.read_text());cases=manifest['cases']
    if [(c['split'],c['case']) for c in cases]!=CASES:raise ValueError('incomplete or changed frozen workload split')
    traces=[]
    for case in cases:
        raw=Path(case['trace']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=case['trace_sha256']:raise ValueError('trace checksum changed')
        trace=json.loads(raw)
        if trace['program_sha256']!=case['program_sha256']:raise ValueError('program mismatch')
        traces.append(trace)
    started=time.perf_counter();merged,ranges=combine(traces)
    a,records,nroots,_=prepare(merged);roles=typed_roles(merged,normalize_effects=True)
    prep=time.perf_counter()-started
    masks=[(a['ordinals']>lo)&(a['ordinals']<=hi) for lo,hi in ranges]
    train=np.logical_or.reduce([m for m,c in zip(masks,cases) if c['split']=='train'])&~a['unsupported']
    valid=np.logical_or.reduce([m for m,c in zip(masks,cases) if c['split']=='validation'])&~a['unsupported']
    assert mx.metal.is_available();mx.set_default_device(mx.gpu)
    started=time.perf_counter();ga={k:mx.array(a[k]) for k in ('owners','roots','local_roots','roles','scalars','left','right','pair_owner')};groles=mx.array(roles)
    rng=np.random.default_rng(803);w=[mx.array(rng.normal(0,1/np.sqrt(i),(i,j)).astype(np.float32)) for i,j in [(16,32),(32,64),(32,64),(256,256)]]
    mx.eval(ga,groles,w);upload=time.perf_counter()-started
    encode=mx.compile(lambda data:structured_encode(data,groles,nroots,len(records),w))
    started=time.perf_counter();features=encode(ga);mx.eval(features);encode_seconds=time.perf_counter()-started
    x=np.array(features);started=time.perf_counter();coef,config=select(x,a['labels'],train,valid);fit_seconds=time.perf_counter()-started
    gcoef=mx.array(coef);fused=mx.compile(lambda data:structured_encode(data,groles,nroots,len(records),w)@gcoef)
    started=time.perf_counter();prediction=fused(ga);mx.eval(prediction);gpu_seconds=time.perf_counter()-started
    scores=np.array(prediction);np.testing.assert_allclose(scores,x@coef,rtol=1e-3,atol=3e-4)
    args.proposals.mkdir(parents=True,exist_ok=True);results=[]
    train_rows={hashlib.sha256(row.tobytes()).digest() for row in x[train]}
    pair_sets=np.array([merged['recipe']['rules'][int(r)]['metadata'].get('source_set','') for r in a['rids']])
    for case,trace,mask in zip(cases,traces,masks):
        out=args.proposals/(case['case']+'.json')
        out.write_text(json.dumps(proposal_packets(trace,scores[mask],config['threshold'])))
        results.append(dict(case=case['case'],split=case['split'],program_sha256=case['program_sha256'],trace_sha256=case['trace_sha256'],metrics=metrics(scores[mask],a['labels'][mask],config['threshold']),unsupported_pairs=int(a['unsupported'][mask].sum()),exact_feature_rows_seen_training=sum(hashlib.sha256(row.tobytes()).digest() in train_rows for row in x[mask]),per_ruleset={name:metrics(scores[mask & (pair_sets==name)],a['labels'][mask & (pair_sets==name)],config['threshold']) for name in sorted(set(pair_sets[mask]))}))
    out=dict(scope='full-workload Cell Eq prediction; actual Metal floating inference; CPU matched-input replay',model='alias_normalized_roles fixed architecture from preceding experiment',config=config,backpropagation=False,workload_split_frozen_before_capture=True,cases=results,cpu_prepare_seconds=prep,upload_seconds=upload,gpu_encode_first_seconds=encode_seconds,ridge_fit_seconds=fit_seconds,gpu_fused_first_seconds=gpu_seconds,cells=len(records),ports=len(a['roots']),candidate_pairs=len(scores),gpu_completed_bindings=0,limitations=['Observed input-port Eq only, not scalar or new-node outputs','CPU provides matches and root routing; no autonomous GPU saturation','Test is one preselected workload, not a broad generalization result','Cold timings are diagnostics, not an end-to-end speed benchmark'])
    args.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))

if __name__=='__main__':main()
