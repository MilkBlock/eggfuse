"""Matched continuous/own-symbol training with fresh structural signatures."""
import sys,argparse,json,hashlib,time
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task import generate
from network import Generator
from typed_model import TypedGenerator
from data import fresh,signature,successor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'depth'))
from probe import rollout,reference,audit
from train import objective as depth_objective


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--representation',choices=['continuous','typed'],required=True);p.add_argument('--seed',type=int,required=True);a=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);mx.random.seed(a.seed);a.output.mkdir(parents=True,exist_ok=True)
    train=[]
    for i,(r,l) in enumerate(((2,3),(3,2),(2,4),(4,2))):
        for f,family in enumerate(('short_cycles','functional')):train.append(generate(r,l,512,14000+2*i+f,family))
    targets=[reference(d['a'],d['b'],4) for d in train]
    final=dict(two_tails=fresh(8,2,256,41817,'two_tails'),cycle_tail=fresh(3,4,256,41818,'two_cycle_tail'))
    training_signatures={signature(successor(x,y)) for d in train for x,y in zip(d['a'],d['b'])}
    prior=set()
    for root in ('multi-row-generation-direction-20261118','multi-row-depth-20261118'):
        for path in (Path('/Volumes/EggFuseWorkspace/experiments')/root).glob('*/*.npz'):
            with np.load(path) as z:
                if 'a' in z and 'b' in z:
                    prior.update(signature(successor(x,y)) for x,y in zip(z['a'],z['b']))
    signatures={name:sorted({signature(successor(x,y)) for x,y in zip(d['a'],d['b'])}) for name,d in final.items()}
    for name,sigs in signatures.items():
        assert not set(sigs)&training_signatures,name
        assert not set(sigs)&prior,(name,'already inspected shape')
    protocol=dict(representation=a.representation,seed=a.seed,mode='independent',steps=6000,lr=.001,batch=64,training_graphs=4096,training_depths=[2,3,4],evaluation_depth=12,
        final_signatures=signatures,training_shape_count=len(training_signatures),previous_shape_count=len(prior),
        final_input_hashes={name:hashlib.sha256(d['a'].tobytes()+d['b'].tobytes()).hexdigest() for name,d in final.items()},
        source_sha256={str(p.relative_to(Path(__file__).resolve().parents[1])):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(__file__).parent/'typed_model.py',Path(__file__).parent/'data.py',Path(__file__).resolve().parents[1]/'network.py',Path(__file__).resolve().parents[1]/'depth/probe.py']},
        teacher_intermediate_states=False,tokenizer='own argmax symbols with straight-through gradients' if a.representation=='typed' else 'raw continuous state')
    (a.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    model=TypedGenerator('independent') if a.representation=='typed' else Generator('independent')
    optimizer=optim.Adam(learning_rate=.001);gradient=nn.value_and_grad(model,depth_objective);rng=np.random.default_rng(a.seed);history=[];start=time.perf_counter()
    for step in range(6000):
        index=step%len(train);d=train[index];depth=2+(step//len(train))%3;ix=rng.integers(512,size=64);pointers,fields=targets[index]
        value,g=gradient(model,mx.array(d['x_a'][ix]),mx.array(d['x_b'][ix]),mx.array(d['coords_a']),mx.array(d['coords_b']),mx.array(d['coords_pair']),d['length'],depth,mx.array(pointers[:depth,ix]),mx.array(fields[:depth,ix]))
        optimizer.update(model,g);mx.eval(value,model.parameters(),optimizer.state)
        if step%1000==0 or step==5999:
            item=dict(step=step+1,loss=float(value),seconds=time.perf_counter()-start);history.append(item);print(json.dumps(item),flush=True)
    model.save_weights(str(a.output/'model.safetensors'))
    panels=dict(train_replay=train[6],**final);outputs={}
    for name,d in panels.items():
        fn=mx.compile(lambda x,y:rollout(model,x,y,mx.array(d['coords_a']),mx.array(d['coords_b']),mx.array(d['coords_pair']),d['length'],12));chunks=[]
        for i in range(0,256,64):
            out=fn(mx.array(d['x_a'][i:i+64]),mx.array(d['x_b'][i:i+64]));mx.eval(out);chunks.append({k:np.array(v) for k,v in out.items()})
        outputs[name]={k:np.concatenate([c[k] for c in chunks],axis=1) for k in chunks[0]}
    # Only now inspect decoded outputs against source-derived path semantics.
    w,b=model.semantic_readout() if a.representation=='typed' else (model.decoder.weight,model.decoder.bias)
    mx.eval(w,b);reports={}
    for name,d in panels.items():
        out=outputs[name];reports[name]=audit(d['a'][:256],d['b'][:256],d['coords_a'],d['coords_b'],d['coords_pair'],d['length'],out,np.array(w),np.array(b))
        np.savez_compressed(a.output/f'{name}.npz',a=d['a'][:256],b=d['b'][:256],coords_a=d['coords_a'],coords_b=d['coords_b'],coords_pair=d['coords_pair'],semantic_weight=np.array(w),semantic_bias=np.array(b),**out)
        print(name,reports[name]['cumulative_exact_graphs'],flush=True)
    result=dict(protocol=protocol,training=history,panels=reports,model_sha256=hashlib.sha256((a.output/'model.safetensors').read_bytes()).hexdigest(),
        status='pass' if all(v['cumulative_exact_graphs'][-1]==v['graphs'] and v['readout_binding_agrees'] for v in reports.values()) else 'difference',
        cpu_corrections=0,scope='matched 12-round generated-token interface experiment, not full egraph engine')
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if result['status']!='pass':raise SystemExit(1)

if __name__=='__main__':main()
