"""Frozen-weight depth stress: repeatedly compose GENERATED keyed Cell states.

This extends the two-round task to a homogeneous keyed-path interface. It does
not retroactively change the original two-round acceptance results.
"""
import sys,json,argparse,hashlib
from pathlib import Path
import numpy as np
import mlx.core as mx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from network import Generator
from task import KEYS,VALUES


def inputs(a,b):
    batch,n=a.shape[:2]
    xa=np.concatenate((np.eye(KEYS)[a[:,:,0]],np.zeros((batch,n,KEYS)),np.eye(VALUES)[a[:,:,1]],np.broadcast_to([1,0],(batch,n,2))),-1).astype(np.float32)
    xb=np.concatenate((np.eye(KEYS)[b[:,:,0]],np.eye(KEYS)[b[:,:,1]],np.eye(VALUES)[b[:,:,2]],np.broadcast_to([0,1],(batch,n,2))),-1).astype(np.float32)
    return xa,xb


def rollout(model,a,b,pa,pb,pp,length,rounds):
    first=model.forward(a,b,pa,pb,pp)
    logits=[first['pointer_logits'][0],first['pointer_logits'][1]]
    latents=[first['latent'][0],first['latent'][1]]
    fields=[first['field_logits'][0],first['field_logits'][1]]
    addresses=[first['addresses'][0],first['addresses'][1]]
    current=latents[-1]
    for step in range(2,rounds):
        parent_positions=pa+mx.array([0,(step+1)*length],mx.int32)
        scores,current,values=model.emit(model.prepare(current,current,parent_positions,parent_positions,1))
        pointers=mx.stop_gradient(mx.argmax(scores,-1))
        logits.append(scores);latents.append(current);fields.append(values);addresses.append(parent_positions[pointers])
    return dict(pointer_logits=mx.stack(logits),latent=mx.stack(latents),field_logits=mx.stack(fields),
                addresses=mx.stack(addresses),pointers=mx.stop_gradient(mx.argmax(mx.stack(logits),-1)))


def decode(logits):
    cols=[];at=0
    for width in (KEYS,KEYS,VALUES,VALUES):cols.append(logits[...,at:at+width].argmax(-1));at+=width
    return np.stack(cols,-1)


def reference(a,b,rounds):
    """Independent source-edge path composition; never part of neural forward."""
    batch,n=a.shape[:2];all_ptr=[];all_fields=[]
    for g in range(batch):
        lookup={int(row[0]):j for j,row in enumerate(b[g])}
        p=np.array([lookup[int(row[0])] for row in a[g]],np.int32)
        f=np.stack((a[g,:,0],b[g,p,1],a[g,:,1],b[g,p,2]),-1)
        ps=[p];fs=[f]
        for _ in range(1,rounds):
            lookup={int(row[0]):j for j,row in enumerate(f)}
            p=np.array([lookup[int(row[1])] for row in f],np.int32)
            f=np.stack((f[:,0],f[p,1],f[:,2],f[p,3]),-1)
            ps.append(p);fs.append(f)
        all_ptr.append(ps);all_fields.append(fs)
    return np.array(all_ptr).transpose(1,0,2),np.array(all_fields).transpose(1,0,2,3)


def audit(a,b,pa,pb,pp,length,out,weight,bias):
    rounds=len(out['latent']);ptr,truth=reference(a,b,rounds)
    decoded=decode(out['latent'].astype(np.float64)@weight.astype(np.float64).T+bias.astype(np.float64))
    advertised=decode(out['field_logits']);binding=(decoded==advertised).all(axis=(2,3))
    pointer=(out['pointers']==ptr).all(-1);values=(decoded==truth).all(axis=(2,3));addresses=[]
    for step in range(rounds):
        positions=pb if step==0 else pa+np.array([0,(step+1)*length],np.int32)
        addresses.append((out['addresses'][step]==positions[ptr[step]]).all(axis=(1,2)))
    legal=pointer&values&binding&np.array(addresses)
    cumulative=np.logical_and.accumulate(legal,axis=0)
    return dict(graphs=len(a),rounds=rounds,round_exact_graphs=legal.sum(1).tolist(),
        cumulative_exact_graphs=cumulative.sum(1).tolist(),pointer_exact_graphs=pointer.sum(1).tolist(),
        field_exact_graphs=values.sum(1).tolist(),readout_binding_agrees=bool(binding.all()),
        first_failing_round=[int(np.flatnonzero(~cumulative[:,g])[0])+1 if not cumulative[-1,g] else None for g in range(len(a))])


def main():
    p=argparse.ArgumentParser();p.add_argument('artifact',type=Path);p.add_argument('output',type=Path);p.add_argument('--rounds',type=int,default=8);args=p.parse_args()
    if args.rounds<2:raise ValueError('at least two rounds')
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu)
    meta=json.loads((args.artifact/'result.json').read_text());m=Generator(meta['protocol']['mode']);m.load_weights(str(args.artifact/'model.safetensors'))
    results={};raw={}
    for panel in ('seen','long_cycle','final_fanin_rows'):
        with np.load(args.artifact/f'{panel}.npz') as data:
            a=data['a'];b=data['b'];pa=data['coords_a'];pb=data['coords_b'];pp=data['coords_pair']
        length=int(np.max(pa[:,1]))+1
        f=mx.compile(lambda x,y:rollout(m,x,y,mx.array(pa),mx.array(pb),mx.array(pp),length,args.rounds))
        xa,xb=inputs(a,b);chunks=[]
        for start in range(0,len(a),64):
            out=f(mx.array(xa[start:start+64]),mx.array(xb[start:start+64]));mx.eval(out)
            chunks.append({k:np.array(v) for k,v in out.items()})
        raw[panel]=(a,b,pa,pb,pp,length,{k:np.concatenate([c[k] for c in chunks],axis=1) for k in chunks[0]})
    # No oracle until every closed-loop device trajectory has finished.
    for name,(a,b,pa,pb,pp,length,out) in raw.items():
        results[name]=audit(a,b,pa,pb,pp,length,out,np.array(m.decoder.weight),np.array(m.decoder.bias))
        print(name,results[name]['cumulative_exact_graphs'],flush=True)
    report=dict(scope='frozen-weight repeated keyed-Cell composition; no original-input access after round 1',
        mode=meta['protocol']['mode'],seed=meta['protocol']['seed'],model_sha256=meta['model_sha256'],
        trained_rounds=2,probe_rounds=args.rounds,weights_changed=False,cpu_corrections=0,panels=results,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=['declared homogeneous path-composition extension, not arbitrary new rules','no union or free output allocation','not a speed benchmark'])
    args.output.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
