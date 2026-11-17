"""Fixed longer-rollout fine tuning; never inserts a teacher latent between steps."""
import sys,argparse,json,hashlib,time
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task import generate,KEYS,VALUES
from network import Generator
from probe import rollout,reference,audit,inputs


def tail_graphs(rows,length,count,seed):
    d=generate(rows,length,count,seed,'functional');rng=np.random.default_rng(seed+17);n=rows*length
    for g in range(count):
        order=rng.permutation(d['a'][g,:,0]);edge={int(order[i]):int(order[min(i+1,n-1)]) for i in range(n)}
        d['b'][g,:,1]=[edge[int(key)] for key in d['b'][g,:,0]]
    d['x_a'],d['x_b']=inputs(d['a'],d['b']);d['family']='long_tail'
    for name in ('targets','fields','cycle_keys'):d.pop(name,None)
    return d


def objective(model,xa,xb,pa,pb,pp,length,depth,ptr,fields):
    out=rollout(model,xa,xb,pa,pb,pp,length,depth);scores=out['pointer_logits']
    loss=nn.losses.cross_entropy(scores.reshape(-1,scores.shape[-1]),ptr.reshape(-1),reduction='mean');offset=0
    for column,width in enumerate((KEYS,KEYS,VALUES,VALUES)):
        s=out['field_logits'][...,offset:offset+width]
        loss+=nn.losses.cross_entropy(s.reshape(-1,width),fields[...,column].reshape(-1),reduction='mean');offset+=width
    return loss


def main():
    p=argparse.ArgumentParser();p.add_argument('parent',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);meta=json.loads((args.parent/'result.json').read_text());seed=meta['protocol']['seed'];mode=meta['protocol']['mode']
    assert hashlib.sha256((args.parent/'model.safetensors').read_bytes()).hexdigest()==meta['model_sha256']
    mx.random.seed(seed);model=Generator(mode);model.load_weights(str(args.parent/'model.safetensors'));args.output.mkdir(parents=True,exist_ok=True)
    train=[generate(r,l,1024,1200+i,'short_cycles') for i,(r,l) in enumerate(((2,3),(3,2),(2,4),(4,2)))]
    target=[reference(d['a'],d['b'],4) for d in train]
    final=dict(tail_rows=tail_graphs(8,2,256,31817),tail_layout=tail_graphs(3,4,256,31818))
    protocol=dict(parent_model_sha256=meta['model_sha256'],mode=mode,seed=seed,steps=3000,lr=.0003,batch=64,training_depths=[2,3,4],evaluation_depth=12,
        final_input_sha256={k:hashlib.sha256(v['a'].tobytes()+v['b'].tobytes()).hexdigest() for k,v in final.items()},
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))},
        checkpoint_policy='final fixed step; no heldout-driven tuning')
    (args.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    opt=optim.Adam(learning_rate=.0003);grad=nn.value_and_grad(model,objective);rng=np.random.default_rng(seed);history=[];start=time.perf_counter()
    for step in range(3000):
        index=step%4;depth=2+(step//4)%3;d=train[index];ix=rng.integers(1024,size=64);pt,ft=target[index]
        value,g=grad(model,mx.array(d['x_a'][ix]),mx.array(d['x_b'][ix]),mx.array(d['coords_a']),mx.array(d['coords_b']),mx.array(d['coords_pair']),d['length'],depth,mx.array(pt[:depth,ix]),mx.array(ft[:depth,ix]))
        opt.update(model,g);mx.eval(value,model.parameters(),opt.state)
        if step%500==0 or step==2999:
            record=dict(step=step+1,depth=depth,loss=float(value),seconds=time.perf_counter()-start);history.append(record);print(json.dumps(record),flush=True)
    model.save_weights(str(args.output/'model.safetensors'))
    panels=dict(train_replay=train[2],**final);outputs={}
    for name,d in panels.items():
        fn=mx.compile(lambda a,b:rollout(model,a,b,mx.array(d['coords_a']),mx.array(d['coords_b']),mx.array(d['coords_pair']),d['length'],12));chunks=[]
        count=256
        for start in range(0,count,64):
            r=fn(mx.array(d['x_a'][start:start+64]),mx.array(d['x_b'][start:start+64]));mx.eval(r);chunks.append({k:np.array(v) for k,v in r.items()})
        outputs[name]={k:np.concatenate([r[k] for r in chunks],axis=1) for k in chunks[0]}
    reports={}
    for name,d in panels.items():
        out=outputs[name];reports[name]=audit(d['a'][:256],d['b'][:256],d['coords_a'],d['coords_b'],d['coords_pair'],d['length'],out,np.array(model.decoder.weight),np.array(model.decoder.bias))
        np.savez_compressed(args.output/f'{name}.npz',a=d['a'][:256],b=d['b'][:256],coords_a=d['coords_a'],coords_b=d['coords_b'],coords_pair=d['coords_pair'],decoder_weight=np.array(model.decoder.weight),decoder_bias=np.array(model.decoder.bias),**out)
        print(name,reports[name]['cumulative_exact_graphs'],flush=True)
    result=dict(protocol=protocol,panels=reports,training=history,model_sha256=hashlib.sha256((args.output/'model.safetensors').read_bytes()).hexdigest(),
        status='pass' if all(r['cumulative_exact_graphs'][-1]==r['graphs'] and r['readout_binding_agrees'] for r in reports.values()) else 'difference',
        cpu_corrections=0,teacher_latents=False,scope='repeated generated keyed-Cell composition; no free allocation, union or eggcc')
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if result['status']!='pass':raise SystemExit(1)

if __name__=='__main__':main()
