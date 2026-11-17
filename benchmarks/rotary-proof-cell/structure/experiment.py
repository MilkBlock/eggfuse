"""Frozen structural holdouts; no test-driven checkpoint selection or state repair."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from importlib.metadata import version
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from spec import *
from semantics import targets, audit, decode
from network import StructureNet, loss


def unique_cases(group,n,rng,exclude=()):
    used=set(map(tuple,exclude));out=[]
    while len(out)<n:
        for row in sample(group,max(512,n-len(out)),rng):
            key=tuple(row)
            if key not in used:used.add(key);out.append(row)
            if len(out)==n:break
    return np.array(out,np.int32)


def host(result):
    mx.eval(result)
    return {k:np.array(v) for k,v in result.items()}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('output',type=Path);p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--steps',type=int,default=12000);p.add_argument('--weights',type=Path)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if not mx.metal.is_available():raise RuntimeError('Metal required; no CPU inference fallback')
    mx.set_default_device(mx.gpu);mx.random.seed(args.seed)
    rng=np.random.default_rng(4821)
    train=unique_cases('seen',32768,rng)
    datasets={'train_replay':train[rng.choice(len(train),2048,replace=False)]}
    for group in GROUPS:datasets[group]=unique_cases(group,2048,rng,train if group=='seen' else ())
    locs={group:positions(len(cases),rng) for group,cases in datasets.items()}
    protocol=dict(seed=args.seed,steps=args.steps,train_cases=len(train),batch_size=128,learning_rate=0.002,
        checkpoint_policy='final fixed step only; no holdout evaluation before training completes',
        split_manifest=manifest(),dataset_hashes={k:digest(v) for k,v in dict(train=train,**datasets).items()},
        input_features=INPUT_WIDTH,latent_width=DIM,output_logits=WIDTH,
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))})
    (args.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    np.savez_compressed(args.output/'inputs.npz',train=train,**datasets)
    # Only training cases are executed by the offline teacher before fitting.
    x=seed_inputs(train);truth=targets(train)
    model=StructureNet();history=[]
    if args.weights:model.load_weights(str(args.weights))
    else:
        opt=optim.Adam(learning_rate=0.002);grad=nn.value_and_grad(model,loss)
        batch_rng=np.random.default_rng(args.seed);start=time.perf_counter()
        for step in range(args.steps):
            ix=batch_rng.integers(len(train),size=128)
            value,g=grad(model,mx.array(x[ix]),mx.array(positions(len(ix),batch_rng)),
                         {k:mx.array(v[:,ix]) for k,v in truth.items()})
            opt.update(model,g);mx.eval(value,model.parameters(),opt.state)
            if step%1000==0 or step+1==args.steps:
                record=dict(step=step+1,loss=float(value),seconds=time.perf_counter()-start)
                history.append(record);print(json.dumps(record),flush=True)
        model.save_weights(str(args.output/'model.safetensors'))
    # Finish every GPU trajectory and read before starting semantic verification.
    run=mx.compile(lambda inp,pos:model.rollout(inp,pos))
    predictions={};mask_checks={}
    for group,cases in datasets.items():
        pieces=[];poisoned_pieces=[]
        for start in range(0,len(cases),256):
            end=start+256;pos=mx.array(locs[group][start:end])
            device=run(mx.array(seed_inputs(cases[start:end])),pos)
            poisoned=model.read_old(device['tokens'][2],device['locations'][2],device['owners'][2],device['tokens'][1],pos,True)
            pieces.append(host(device));poisoned_pieces.append(host(poisoned))
        predictions[group]={k:np.concatenate([r[k] for r in pieces],axis=1 if k in ('tokens','locations','logits','owners') else 0) for k in pieces[0]}
        bad={k:np.concatenate([r[k] for r in poisoned_pieces],axis=0) for k in poisoned_pieces[0]}
        pred=predictions[group];retired=decode(pred['logits'])['retired'][2,:,0].astype(bool)
        keys=('read_roles','read_ports','read_payload','read_eq','read_valid')
        mask_checks[group]=dict(predicted_retirements=int(retired.sum()),
            read_unchanged=all(np.array_equal(pred[k][retired],bad[k][retired]) for k in keys),
            no_retired_bank_access=bool(np.all(~bad['old_active'][retired]) and np.all(bad['old_visible'][retired]==0)))
    # Causality probes use the actual generated token, not oracle intermediate states.
    inp=mx.array(seed_inputs(datasets['train_replay'][:32]));pos=mx.array(locs['train_replay'][:32])
    trace=model.rollout(inp,pos,read=False)
    next_token,_,_,_=model.advance(trace['tokens'][1],trace['locations'][1],2,pos)
    _,_,corrupt_scores,_=model.advance(mx.zeros_like(trace['tokens'][1]),trace['locations'][1],2,pos)
    gradient=mx.grad(lambda v:mx.sum(model.rollout(v,pos,read=False)['logits'][2]**2))(inp)
    mx.eval(trace,next_token,corrupt_scores,gradient)
    normal=decode(np.array(trace['logits'][2]));corrupt=decode(np.array(corrupt_scores))
    changed=np.zeros(32,bool)
    for k in SPECS:changed |= np.any((normal[k]!=corrupt[k]).reshape(32,-1),axis=1)
    lineage=dict(direct_recurrence_bitwise_equal=bool(np.array_equal(next_token,trace['tokens'][2])),
                 initial_input_gradient_max=float(mx.max(mx.abs(gradient))),
                 corrupt_second_latent_changes_decoded_third=int(changed.sum()),cases=32)
    # Independent CPU audit starts here. None of its outputs enter the GPU.
    weight=np.array(model.decoder.weight);bias=np.array(model.decoder.bias)
    reports={}
    for group,cases in datasets.items():
        pred=predictions[group]
        report=audit(cases,locs[group],pred,weight,bias);reports[group]=report
        np.savez_compressed(args.output/f'{group}-checkpoints.npz',cases=cases,positions=locs[group],
                            decoder_weight=weight,decoder_bias=bias,**pred)
        print(json.dumps(dict(group=group,passed=report['passed'],cases=report['cases'],
            stage_passed=report['stage_passed'],false_transfers=report['false_transfers'],missed_transfers=report['missed_transfers'])),flush=True)
    checkpoint=args.weights or args.output/'model.safetensors'
    report=dict(experiment_completed=True,semantic_status='pass' if all(r['passed']==r['cases'] for r in reports.values()) else 'difference',
        seed=args.seed,protocol=protocol,groups=reports,mask_checks=mask_checks,lineage=lineage,training=history,
        checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        device=str(mx.default_device()),environment=dict(platform=platform.platform(),python=platform.python_version(),mlx=version('mlx'),numpy=version('numpy')),
        cpu_corrections=0,teacher_latents_used=False,seed_encodings_per_rollout=1,
        scope='standalone structural generalization experiment, not actual egglog runtime',
        limitations=['expanded ABI trained from scratch; not the original 20-pattern checkpoint',
                     'fixed size: four leaves, four F/H constructors, at most one new G member',
                     'fixed three Run schedule and manually specified proof vocabulary',
                     'no bitwise canonicalization, arbitrary-size graphs, iterative Bake or speedup claim'])
    (args.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    if report['semantic_status']!='pass':sys.exit(1)

if __name__=='__main__':main()
