import sys,argparse,json,hashlib,time
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from causal_model import CausalGenerator
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task import generate,KEYS,VALUES
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'depth'))
from probe import reference,audit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'typed'))
from data import fresh


def objective(model,a,b,pa,pb,length,rows,pointer,fields):
    result=model.forward_grouped(a,b,pa,pb,length,rows,2,'serial');scores=result['pointer_logits']
    value=nn.losses.cross_entropy(scores.reshape(-1,scores.shape[-1]),pointer.reshape(-1),reduction='mean');at=0
    for col,width in enumerate((KEYS,KEYS,VALUES,VALUES)):
        x=result['field_logits'][...,at:at+width];value+=nn.losses.cross_entropy(x.reshape(-1,width),fields[...,col].reshape(-1),reduction='mean');at+=width
    return value


def main():
    p=argparse.ArgumentParser();p.add_argument('parent',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu);meta=json.loads((a.parent/'result.json').read_text());seed=meta['protocol']['seed']
    assert meta['protocol']['mode']=='joint'
    assert hashlib.sha256((a.parent/'model.safetensors').read_bytes()).hexdigest()==meta['model_sha256']
    mx.random.seed(seed);model=CausalGenerator();model.load_weights(str(a.parent/'model.safetensors'));a.output.mkdir(parents=True,exist_ok=True)
    train=[generate(r,l,1024,1200+i,'short_cycles') for i,(r,l) in enumerate(((2,3),(3,2),(2,4),(4,2)))]
    final=dict(two_tails=fresh(8,2,256,41817,'two_tails'),cycle_tail=fresh(3,4,256,41818,'two_cycle_tail'))
    protocol=dict(seed=seed,parent_model_sha256=meta['model_sha256'],steps=3000,lr=.0003,batch=64,grouping='serial',teacher_cache=False,
        final_input_hashes={name:hashlib.sha256(d['a'].tobytes()+d['b'].tobytes()).hexdigest() for name,d in final.items()},
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))})
    (a.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    opt=optim.Adam(learning_rate=.0003);grad=nn.value_and_grad(model,objective);rng=np.random.default_rng(seed);history=[];start=time.perf_counter()
    for step in range(3000):
        d=train[step%4];ix=rng.integers(1024,size=64)
        value,g=grad(model,mx.array(d['x_a'][ix]),mx.array(d['x_b'][ix]),mx.array(d['coords_a']),mx.array(d['coords_b']),d['length'],d['rows'],mx.array(d['targets'][:,ix]),mx.array(d['fields'][:,ix]))
        opt.update(model,g);mx.eval(value,model.parameters(),opt.state)
        if step%500==0 or step==2999:
            item=dict(step=step+1,loss=float(value),seconds=time.perf_counter()-start);history.append(item);print(json.dumps(item),flush=True)
    model.save_weights(str(a.output/'model.safetensors'));panels=dict(train_replay=train[2],**final);outputs={}
    for name,d in panels.items():
        f=mx.compile(lambda x,y:model.forward_grouped(x,y,mx.array(d['coords_a']),mx.array(d['coords_b']),d['length'],d['rows'],2,'serial'));chunks=[]
        for i in range(0,256,64):
            out=f(mx.array(d['x_a'][i:i+64]),mx.array(d['x_b'][i:i+64]));mx.eval(out);chunks.append({k:np.array(v) for k,v in out.items()})
        outputs[name]={k:np.concatenate([r[k] for r in chunks],axis=1) for k in chunks[0]}
    reports={}
    for name,d in panels.items():
        out=outputs[name];reports[name]=audit(d['a'][:256],d['b'][:256],d['coords_a'],d['coords_b'],d['coords_pair'],d['length'],out,np.array(model.decoder.weight),np.array(model.decoder.bias))
        np.savez_compressed(a.output/f'{name}.npz',a=d['a'][:256],b=d['b'][:256],coords_a=d['coords_a'],coords_b=d['coords_b'],coords_pair=d['coords_pair'],decoder_weight=np.array(model.decoder.weight),decoder_bias=np.array(model.decoder.bias),**out)
        print(name,reports[name]['cumulative_exact_graphs'],flush=True)
    result=dict(protocol=protocol,panels=reports,training=history,model_sha256=hashlib.sha256((a.output/'model.safetensors').read_bytes()).hexdigest(),
        status='pass' if all(r['cumulative_exact_graphs'][-1]==r['graphs'] for r in reports.values()) else 'difference',cpu_corrections=0,
        scope='genuine causal K/V-cached conditional generator on the bounded two-round Cell task')
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if result['status']!='pass':raise SystemExit(1)

if __name__=='__main__':main()
