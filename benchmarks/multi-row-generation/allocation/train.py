"""Train unanchored output sets. Hungarian truth assignment is training-only."""
import argparse,json,time,hashlib
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from data import generate,coordinates,fingerprint,shape,audit
from assignment import assign
from model import SetGenerator,loss,assignment_cost,decode,verify


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--mode',choices=['joint','independent'],required=True);p.add_argument('--seed',type=int,required=True);a=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal GPU required')
    mx.set_default_device(mx.gpu);mx.random.seed(a.seed);a.output.mkdir(parents=True,exist_ok=True)
    train=generate(4096,51900);seen={fingerprint(x,y) for x,y in zip(train['a'],train['b'])};known={shape(x,y) for x,y in zip(train['a'],train['b'])}
    panels=dict(iid=generate(256,51917,forbidden=seen),multiplicity=generate(256,51918,True,seen))
    held={shape(x,y) for x,y in zip(panels['multiplicity']['a'],panels['multiplicity']['b'])};assert not held&known
    protocol=dict(mode=a.mode,seed=a.seed,steps=4000,lr=.001,batch=32,training_graphs=4096,training_seed=51900,assignment='CPU Hungarian during training only',
        training_shape_count=len(known),held_shape_count=len(held),shape_overlap=0,layouts=[[4,2],[2,4]],
        final_input_hashes={k:hashlib.sha256(d['a'].tobytes()+d['b'].tobytes()).hexdigest() for k,d in panels.items()},
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))})
    (a.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    m=SetGenerator(a.mode);opt=optim.Adam(learning_rate=.001);gradient=nn.value_and_grad(m,loss);rng=np.random.default_rng(a.seed);history=[];start=time.perf_counter();assign_seconds=0
    coords=[tuple(map(mx.array,coordinates(*layout))) for layout in ((4,2),(2,4))]
    for step in range(4000):
        ix=rng.integers(4096,size=32);x=mx.array(train['x'][ix]);target=train['targets'][ix];sp,op=coords[step%2]
        cost=assignment_cost(m(x,sp,op),mx.array(target));mx.eval(cost)
        before=time.perf_counter();mapping=assign(np.array(cost));assign_seconds+=time.perf_counter()-before
        aligned=mx.array(target[np.arange(32)[:,None],mapping]);value,g=gradient(m,x,sp,op,aligned);opt.update(m,g);mx.eval(value,m.parameters(),opt.state)
        if step%500==0 or step==3999:
            item=dict(step=step+1,loss=float(value),seconds=time.perf_counter()-start,assignment_seconds=assign_seconds);history.append(item);print(json.dumps(item),flush=True)
    m.save_weights(str(a.output/'model.safetensors'));outputs={}
    for panel,d in panels.items():
        for layout,(sp,op) in zip(('4x2','2x4'),coords):
            for cut in (False,True) if a.mode=='joint' else (False,):
                name=panel+'-'+layout+('-cut' if cut else '');chunks=[]
                for lo in range(0,256,64):
                    raw=m(mx.array(d['x'][lo:lo+64]),sp,op,cut);out=decode(raw,sp);passed=verify(mx.array(d['a'][lo:lo+64]),mx.array(d['b'][lo:lo+64]),out)
                    mx.eval(raw,out,passed);chunks.append({**{k:np.array(v) for k,v in out.items()},'gpu_pass':np.array(passed),'finite':np.isfinite(np.array(raw['latent'])).all(axis=(1,2))&np.isfinite(np.array(raw['field_logits'])).all(axis=(1,2))})
                outputs[name]=(d,np.array(sp),{k:np.concatenate([c[k] for c in chunks]) for k in chunks[0]})
    # No CPU oracle reads outputs until all device trajectories have completed.
    reports={}
    for name,(d,sp,out) in outputs.items():
        r=audit(d['a'],d['b'],out,sp);assert r['complete_graphs']==int(out['gpu_pass'].sum());assert out['finite'].all();reports[name]=r
        np.savez_compressed(a.output/(name+'.npz'),a=d['a'],b=d['b'],source_pos=sp,**out)
        print(name,{k:r[k] for k in ('complete_graphs','graphs','missing','duplicates','illegal_bindings','count_error_graphs')},flush=True)
    r=dict(protocol=protocol,training=history,panels=reports,status='pass' if all(v['complete_graphs']==v['graphs'] for k,v in reports.items() if not k.endswith('-cut')) else 'difference',
        model_sha256=hashlib.sha256((a.output/'model.safetensors').read_bytes()).hexdigest(),cpu_inference_corrections=0,
        scope='unanchored equality-join set generation; one neural stage, not recurrence or full egraph inference')
    (a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n')
    if r['status']!='pass':raise SystemExit(1)

if __name__=='__main__':main()
