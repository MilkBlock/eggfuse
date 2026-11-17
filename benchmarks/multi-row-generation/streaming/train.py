"""Matched generated-history versus blinded-history multi-row decoders."""
import sys,argparse,json,time,hashlib
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim
from stream_model import StreamGenerator
from stream_data import fresh
from stream_objective import objective
from stream_metrics import check_token,repeat_metrics
from metrics import soft_metrics
from data import generate,coordinates,shape,fingerprint,audit,features
from model import assignment_cost,decode,verify
from assignment import assign


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--arm',choices=['feedback','blind'],required=True);p.add_argument('--seed',type=int,required=True);a=p.parse_args()
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    if (a.output/'model.safetensors').exists():raise RuntimeError('refusing to overwrite a final model')
    mx.set_default_device(mx.gpu);mx.random.seed(a.seed);a.output.mkdir(parents=True,exist_ok=True)
    train=generate(4096,51900);known={shape(x,y) for x,y in zip(train['a'],train['b'])};seen={fingerprint(x,y) for x,y in zip(train['a'],train['b'])}
    root=Path('/Volumes/EggFuseWorkspace/experiments/multi-row-coverage-20261118/control-joint-1703');prior={}
    for panel in ('iid','multiplicity','double_triple','four_left'):
        with np.load(root/f'{panel}-4x2.npz') as z:
            x=z['a'];y=z['b'];prior[panel]=dict(a=x,b=y,x=features(x,y));known.update(shape(i,j) for i,j in zip(x,y));seen.update(fingerprint(i,j) for i,j in zip(x,y))
    final=dict(triple_right=fresh(256,71918,'triple_right',seen),four_right=fresh(256,71919,'four_right',seen))
    shapes={name:{shape(x,y) for x,y in zip(d['a'],d['b'])} for name,d in final.items()};assert all(not v&known for v in shapes.values())
    here=Path(__file__).parent;parent=here.parent
    deps=list(here.glob('*.py'))+[parent/'allocation'/f for f in ('model.py','data.py','assignment.py')]+[parent/'coverage'/f for f in ('objective.py','fixtures.py','metrics.py')]+[parent/'network.py',parent/'task.py']
    protocol=dict(arm=a.arm,seed=a.seed,steps=4000,batch=32,lr=.001,training_seed=51900,training_graphs=4096,teacher_history=False,
        history_width=90,initialization='from scratch; same shapes, seed and RNG sequence in both arms',
        final_shape_counts={k:len(v) for k,v in shapes.items()},shape_overlap=0,
        final_input_hashes={k:hashlib.sha256(d['a'].tobytes()+d['b'].tobytes()).hexdigest() for k,d in final.items()},
        source_sha256={str(p.relative_to(parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in deps})
    (a.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');m=StreamGenerator(a.arm);opt=optim.Adam(learning_rate=.001);grad=nn.value_and_grad(m,objective)
    m.save_weights(str(a.output/'initial.safetensors'));protocol['initial_model_sha256']=hashlib.sha256((a.output/'initial.safetensors').read_bytes()).hexdigest()
    (a.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    layouts=[(r,l,*map(mx.array,coordinates(r,l))) for r,l in ((4,2),(2,4))];rng=np.random.default_rng(a.seed);history=[];start=time.perf_counter()
    for step in range(4000):
        ix=rng.integers(4096,size=32);x=mx.array(train['x'][ix]);target=train['targets'][ix];rows,length,sp,op=layouts[step%2]
        cost=assignment_cost(m(x,sp,op,rows,length),mx.array(target));mx.eval(cost);mapping=assign(np.array(cost));aligned=mx.array(target[np.arange(32)[:,None],mapping])
        value,g=grad(m,x,sp,op,rows,length,aligned);opt.update(m,g);mx.eval(value,m.parameters(),opt.state)
        if step%500==0 or step==3999:
            item=dict(step=step+1,loss=float(value),seconds=time.perf_counter()-start);history.append(item);print(json.dumps(item),flush=True)
    m.save_weights(str(a.output/'model.safetensors'));panels=dict(train_replay={k:v[:256] for k,v in train.items()},**prior,**final);outputs={}
    for panel,d in panels.items():
        for rows,length,sp,op in layouts:
            interventions=('none','erase','local') if a.arm=='feedback' and panel in ('iid','triple_right','four_right') else ('none',)
            for intervention in interventions:
                chunks=[]
                for lo in range(0,256,64):
                    raw=m(mx.array(d['x'][lo:lo+64]),sp,op,rows,length,intervention);decoded=decode(raw,sp);passed=verify(mx.array(d['a'][lo:lo+64]),mx.array(d['b'][lo:lo+64]),decoded)
                    mx.eval(raw,decoded,passed);chunks.append({**{k:np.array(v) for k,v in raw.items()},**{k:np.array(v) for k,v in decoded.items()},'gpu_pass':np.array(passed)})
                name=f'{panel}-{rows}x{length}'+('' if intervention=='none' else '-'+intervention)
                outputs[name]=(d,np.array(sp),length,{k:np.concatenate([c[k] for c in chunks]) for k in chunks[0]})
    # All generation finished before independent source truth is used in audit.
    reports={}
    for name,(d,sp,length,out) in outputs.items():
        check_token(out,sp);r=audit(d['a'],d['b'],out,sp);assert r['complete_graphs']==int(out['gpu_pass'].sum());r['soft']=soft_metrics(d['a'],d['b'],out);r['repeats']=repeat_metrics(out,length);reports[name]=r
        np.savez_compressed(a.output/f'{name}.npz',a=d['a'],b=d['b'],source_pos=sp,**out)
        print(name,r['complete_graphs'],r['repeats'],flush=True)
    result=dict(protocol=protocol,training=history,panels=reports,model_sha256=hashlib.sha256((a.output/'model.safetensors').read_bytes()).hexdigest(),
        status='pass' if all(v['complete_graphs']==v['graphs'] for k,v in reports.items() if not k.endswith(('-erase','-local'))) else 'difference',
        cpu_inference_corrections=0,scope='one-stage row-causal emission, actual generated history; not cross-Run completion or full egraph engine')
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if result['status']!='pass':raise SystemExit(1)

if __name__=='__main__':main()
