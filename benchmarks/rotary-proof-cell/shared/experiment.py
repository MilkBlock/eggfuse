"""Frozen paired comparison; CPU verification starts after GPU predictions finish."""
import argparse,hashlib,json,time,sys,platform
from pathlib import Path
from importlib.metadata import version
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from abi import *
from shared_net import SharedNet,loss,unpack,discrete
from fresh import freeze,freeze_final,register,cases as fresh_cases,final_cases
from spec import seed_inputs,positions,digest
from semantics import targets,audit as baseline_audit
from cpu_contract import audit
from network import StructureNet


def host(out):
    mx.eval(out);return {k:np.array(v) for k,v in out.items()}


def evaluate(model,cases,pos,shared=True):
    run=mx.compile(lambda x,p:model.rollout(x,p));pieces=[];poison=[]
    for start in range(0,len(cases),256):
        p=mx.array(pos[start:start+256]);r=run(mx.array(seed_inputs(cases[start:start+256])),p)
        if shared:
            poisoned=model.read_old(r['tokens'][2],r['locations'][2],r['owners'][2],r['tokens'][1],p,True)
            poison.append(host(poisoned))
        pieces.append(host(r))
    out={k:np.concatenate([r[k] for r in pieces],axis=1 if k in ('tokens','locations','logits','owners') else 0) for k in pieces[0]}
    check={}
    if shared:
        bad={k:np.concatenate([r[k] for r in poison],axis=0) for k in poison[0]}
        retired=out['owners'][2]==2
        check=dict(predicted_retirements=int(retired.sum()),
            unchanged=all(np.array_equal(out[k][retired],bad[k][retired]) for k in ('read_roles','read_ports','read_eq','read_payload','read_valid')),
            old_masked=bool(np.all(~bad['old_active'][retired]) and np.all(bad['old_visible'][retired]==0)))
    return out,check


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--seed',type=int,default=1703)
    p.add_argument('--local-supervision',action='store_true');p.add_argument('--steps',type=int,default=6000);p.add_argument('--old-root',type=Path,required=True);a=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required; no CPU fallback')
    mx.set_default_device(mx.gpu);mx.random.seed(a.seed);a.output.mkdir(parents=True,exist_ok=True)
    manifest=freeze_final() if a.local_supervision else freeze();register(manifest)
    old=a.old_root/f'seed-{a.seed}'
    with np.load(old/'inputs.npz') as z:
        train=z['train'];datasets={k:z[k] for k in z.files if k!='train'}
    locs={}
    for k in datasets:
        with np.load(old/f'{k}-checkpoints.npz') as z:locs[k]=z['positions'];assert np.array_equal(z['cases'],datasets[k])
    for name,hard in [('fresh_shape',False),('fresh_joint',True)]:datasets[name],locs[name]=fresh_cases(manifest,hard)
    if a.local_supervision:
        for name,hard in [('final_shape',False),('final_joint',True)]:datasets[name],locs[name]=final_cases(manifest,hard)
    protocol=dict(local_supervision=a.local_supervision,seed=a.seed,steps=a.steps,train_hash=digest(train),fresh_manifest=manifest,
        dataset_hashes={k:digest(v) for k,v in datasets.items()},latent_floats=TOKEN_WIDTH,
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))},
        old_checkpoint_sha256=hashlib.sha256((old/'model.safetensors').read_bytes()).hexdigest(),
        selection='fixed final step, no test-guided fitting')
    (a.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    np.savez_compressed(a.output/'inputs.npz',train=train,**datasets)
    x=seed_inputs(train);y=targets(train);model=SharedNet();opt=optim.Adam(learning_rate=.002)
    if a.local_supervision:
        from local_supervision import local_loss
        def objective(m,x,p,t):return loss(m,x,p,t)+local_loss(m)
    else:objective=loss
    grad=nn.value_and_grad(model,objective);rng=np.random.default_rng(a.seed);history=[];start=time.perf_counter()
    for step in range(a.steps):
        ix=rng.integers(len(train),size=128)
        value,g=grad(model,mx.array(x[ix]),mx.array(positions(128,rng)),{k:mx.array(v[:,ix]) for k,v in y.items()})
        opt.update(model,g);mx.eval(value,model.parameters(),opt.state)
        if step%500==0 or step+1==a.steps:
            item=dict(step=step+1,loss=float(value),seconds=time.perf_counter()-start);history.append(item);print(json.dumps(item),flush=True)
    weights=a.output/'model.safetensors';model.save_weights(str(weights))
    predictions={};masks={};old_predictions={}
    for name,c in datasets.items():predictions[name],masks[name]=evaluate(model,c,locs[name])
    baseline=StructureNet();baseline.load_weights(str(old/'model.safetensors'))
    for name in datasets:
        if name.startswith(('fresh_','final_')):old_predictions[name],_=evaluate(baseline,datasets[name],locs[name],False)
    # Ablations alter learned weights only. They cannot invoke a reference answer.
    corrupt_predictions={}
    for name,panel in [('relation','union'),('pointer','mapping')]:
        broken=SharedNet();broken.load_weights(str(weights));head=getattr(broken,name)
        head.layers[0].weight=mx.zeros_like(head.layers[0].weight);head.layers[0].bias=mx.zeros_like(head.layers[0].bias)
        head.layers[2].weight=mx.zeros_like(head.layers[2].weight);head.layers[2].bias=mx.full_like(head.layers[2].bias,-20 if name=='relation' else 0)
        corrupt_predictions[name],_=evaluate(broken,datasets[panel][:256],locs[panel][:256])
    # Keep the protected seed intact; erase only the GENERATED relation matrix.
    probe=datasets['seen'][:128];pos=mx.array(locs['seen'][:128]);r=model.rollout(mx.array(seed_inputs(probe)),pos,False)
    token,_,_,_=model.advance(r['tokens'][1],r['locations'][1],2,pos)
    broken=mx.concatenate((mx.zeros_like(r['tokens'][1,:,:64]),r['tokens'][1,:,64:]),axis=-1)
    changed,_,_,_=model.advance(broken,r['locations'][1],2,pos)
    gradient=mx.grad(lambda t:mx.sum(model.advance(t,r['locations'][1],2,pos)[0][:,-1]))(r['tokens'][1])
    mx.eval(r,token,changed,gradient)
    lineage=dict(direct_recurrence_equal=bool(np.array_equal(token,r['tokens'][2])),
        protected_lanes_equal=bool(np.array_equal(np.array(r['tokens'])[:,:,136:275],np.broadcast_to(seed_inputs(probe),(3,len(probe),139)))),
        erased_relation_changes_transfer=int(np.sum((np.array(token)[:,-1]>.5)!=(np.array(changed)[:,-1]>.5))),
        gate_gradient_to_generated_relation=float(mx.max(mx.abs(gradient[:,:64]))))
    # All forward execution is finished. CPU only decodes and rejects/accepts.
    reports={};base_reports={};corrupt_reports={}
    for name,c in datasets.items():
        reports[name]=audit(c,locs[name],predictions[name]);rr=reports[name]
        np.savez_compressed(a.output/f'{name}-checkpoints.npz',cases=c,positions=locs[name],**predictions[name])
        print(json.dumps(dict(group=name,passed=rr['passed'],cases=rr['cases'],stage_passed=rr['stage_passed'])),flush=True)
    for name,pred in old_predictions.items():
        base_reports[name]=baseline_audit(datasets[name],locs[name],pred,np.array(baseline.decoder.weight),np.array(baseline.decoder.bias))
        np.savez_compressed(a.output/f'baseline-{name}.npz',cases=datasets[name],positions=locs[name],decoder_weight=np.array(baseline.decoder.weight),decoder_bias=np.array(baseline.decoder.bias),**pred)
    for name,panel in [('relation','union'),('pointer','mapping')]:corrupt_reports[name]=audit(datasets[panel][:256],locs[panel][:256],corrupt_predictions[name])
    result=dict(experiment_completed=True,semantic_status='pass' if all(r['passed']==r['cases'] for r in reports.values()) else 'difference',
        protocol=protocol,groups=reports,baseline_fresh=base_reports,head_ablation=corrupt_reports,lineage=lineage,masks=masks,
        training=history,checkpoint_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),device=str(mx.default_device()),
        environment=dict(platform=platform.platform(),python=platform.python_version(),mlx=version('mlx'),numpy=version('numpy')),
        cpu_corrections=0,teacher_latents_in_rollout=False,scope='bounded structured neural prototype, not egglog runtime',
        static_work=['protected input copying','schedule','initial identity addressing','proof macro instantiation','GPU feature gathering and matrix composition'],
        learned_work=['shared relation update','shared primitive pointer scoring','LHS activation'],
        limitations=['279 floats instead of 128; no compression claim','fixed 8 old members and at most one new G member','engineered local features and eight recurrent sweeps','no arbitrary-size or bitwise canonical latent guarantee'])
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if result['semantic_status']!='pass':sys.exit(1)

if __name__=='__main__':main()
