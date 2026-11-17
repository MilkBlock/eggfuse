"""Paired loss-only intervention; all inference uses unchanged SetGenerator."""
import sys,argparse,json,time,hashlib,shutil
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from fixtures import fresh
from objective import objective
from metrics import soft_metrics,check_decode
from data import generate,coordinates,shape,fingerprint,audit
from model import SetGenerator,assignment_cost,decode,verify
from assignment import assign


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--mode',choices=['joint','independent'],required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--treatment',choices=['coverage','control'],required=True);args=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    if (args.output/'model.safetensors').exists():raise RuntimeError('refusing to overwrite an existing final model')
    mx.set_default_device(mx.gpu);mx.random.seed(args.seed);args.output.mkdir(parents=True,exist_ok=True)
    parent=Path('/Volumes/EggFuseWorkspace/experiments/multi-row-allocation-20261118')/f'{args.mode}-{args.seed}'
    old=json.loads((parent/'result.json').read_text());assert old['model_sha256']==digest(parent/'model.safetensors')
    assert old['protocol']['steps']==4000 and old['protocol']['training_seed']==51900 and old['protocol']['batch']==32
    train=generate(4096,51900);seen={fingerprint(a,b) for a,b in zip(train['a'],train['b'])};known={shape(a,b) for a,b in zip(train['a'],train['b'])}
    diagnostics={}
    for panel in ('iid','multiplicity'):
        with np.load(parent/(panel+'-4x2.npz')) as z:
            from data import features
            a=z['a'];b=z['b'];diagnostics[panel]=dict(a=a,b=b,x=features(a,b))
            known.update(shape(x,y) for x,y in zip(a,b));seen.update(fingerprint(x,y) for x,y in zip(a,b))
    finals=dict(double_triple=fresh(256,61918,'double_triple',seen),four_left=fresh(256,61919,'four_left',seen))
    final_shapes={name:{shape(a,b) for a,b in zip(d['a'],d['b'])} for name,d in finals.items()}
    assert all(not s&known for s in final_shapes.values())
    here=Path(__file__).parent;allocation=here.parent/'allocation'
    paths=list(here.glob('*.py'))+[allocation/f for f in ('model.py','data.py','assignment.py')]+[here.parent/'network.py',here.parent/'task.py']
    protocol=dict(treatment=args.treatment,mode=args.mode,seed=args.seed,steps=4000,lr=.001,batch=32,training_seed=51900,
        coverage_weight=1.0 if args.treatment=='coverage' else 0.0,count_weight=.25 if args.treatment=='coverage' else 0.0,
        prior_model_sha256=old['model_sha256'],new_shape_counts={k:len(v) for k,v in final_shapes.items()},shape_overlap=0,
        final_input_hashes={k:hashlib.sha256(d['a'].tobytes()+d['b'].tobytes()).hexdigest() for k,d in finals.items()},
        source_sha256={str(p.relative_to(here.parent)):digest(p) for p in paths},inference_network_unchanged=True)
    (args.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');m=SetGenerator(args.mode);history=[]
    coords=[tuple(map(mx.array,coordinates(*layout))) for layout in ((4,2),(2,4))]
    if args.treatment=='control':
        m.load_weights(str(parent/'model.safetensors'));shutil.copyfile(parent/'model.safetensors',args.output/'model.safetensors')
    else:
        optimizer=optim.Adam(learning_rate=.001);gradient=nn.value_and_grad(m,objective);rng=np.random.default_rng(args.seed);start=time.perf_counter()
        for step in range(4000):
            ix=rng.integers(4096,size=32);x=mx.array(train['x'][ix]);target=train['targets'][ix];sp,op=coords[step%2]
            cost=assignment_cost(m(x,sp,op),mx.array(target));mx.eval(cost);mapping=assign(np.array(cost));aligned=mx.array(target[np.arange(32)[:,None],mapping])
            value,g=gradient(m,x,sp,op,aligned);optimizer.update(m,g);mx.eval(value,m.parameters(),optimizer.state)
            if step%500==0 or step==3999:
                r=dict(step=step+1,loss=float(value),seconds=time.perf_counter()-start);history.append(r);print(json.dumps(r),flush=True)
        m.save_weights(str(args.output/'model.safetensors'))
    panels=dict(train_replay={k:v[:256] for k,v in train.items()},**diagnostics,**finals);outputs={}
    for panel,d in panels.items():
        for layout,(sp,op) in zip(('4x2','2x4'),coords):
            chunks=[]
            for lo in range(0,256,64):
                raw=m(mx.array(d['x'][lo:lo+64]),sp,op);out=decode(raw,sp);gpu=verify(mx.array(d['a'][lo:lo+64]),mx.array(d['b'][lo:lo+64]),out);mx.eval(raw,out,gpu)
                chunks.append({**{k:np.array(v) for k,v in out.items()},**{k:np.array(raw[k]) for k in ('active_logits','pointer_logits','field_logits')},'gpu_pass':np.array(gpu)})
            outputs[panel+'-'+layout]=(d,np.array(sp),{k:np.concatenate([c[k] for c in chunks]) for k in chunks[0]})
    reports={}
    for name,(d,sp,out) in outputs.items():
        check_decode(out,sp);r=audit(d['a'],d['b'],out,sp);assert r['complete_graphs']==int(out['gpu_pass'].sum());r['soft']=soft_metrics(d['a'],d['b'],out);reports[name]=r
        np.savez_compressed(args.output/(name+'.npz'),a=d['a'],b=d['b'],source_pos=sp,**out)
        print(name,r['complete_graphs'],r['soft'],flush=True)
    result=dict(protocol=protocol,training=history,panels=reports,model_sha256=digest(args.output/'model.safetensors'),
        status='pass' if all(v['complete_graphs']==v['graphs'] for k,v in reports.items() if k.startswith(('double_triple','four_left'))) else 'difference',
        cpu_inference_corrections=0,scope='unchanged unanchored set decoder, coverage supervision only; not full egraph inference')
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if result['status']!='pass':raise SystemExit(1)

if __name__=='__main__':main()
