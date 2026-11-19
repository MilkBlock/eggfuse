"""Fit admission heads from paired forced-open/closed rollouts of a frozen actor."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
import torch
import torch.nn.functional as F

from gate_model import GateSystem
from gate_data import templates, dataset, SEEDS, INPUTS, array_digest
from credit_ablation.reward import team_reward
from width_ablation.model import WidthSystem
from encoder import EClassSchema

HERE=Path(__file__).resolve().parent
PRICES={'gate_p0':0.0,'gate_p25':.25}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utility(stages, targets, price):
    reward,_ = team_reward(*stages,*targets)
    count=sum(s['gate_open'].sum(dim=1) for s in stages)
    return reward,reward-price*count.float()/16


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('parent',type=Path)
    parser.add_argument('arm',choices=PRICES);parser.add_argument('seed',type=int,choices=SEEDS);a=parser.parse_args()
    from fit import transfer,device,state_digest
    dev=device();price=PRICES[a.arm];frozen=a.root/'fresh-gate-inputs.json';assert frozen.exists()
    out=a.root/f'{a.arm}-{a.seed}';out.mkdir(parents=True,exist_ok=True)
    if (out/'gates.pt').exists():raise FileExistsError(out)
    parent=a.parent/f'supervised-{a.seed}';meta=json.loads((parent/'fit.json').read_text())
    assert digest(parent/'final.pt')==meta['model_sha256']
    ts=[t for t in templates() if t['split']=='train'];schema=EClassSchema(ts)
    m=GateSystem(schema,a.seed).load_actor(torch.load(parent/'final.pt',map_location='cpu',weights_only=True))
    with torch.no_grad():
        for gate in m.gates:
            gate.readout.weight.zero_();gate.readout.bias.fill_(1.0)
    init=state_digest(m.gates.state_dict());actor_init=state_digest(m.actor.state_dict())
    m.to(dev);m.train();opt=torch.optim.Adam(m.gates.parameters(),lr=.002)
    panels={t['id']:dataset('train',t) for t in ts}
    with torch.no_grad():
        tables={t['id']:m.encoder.encode_bank(schema.bank(t,'pairwise',dev)).detach() for t in ts}
    rng=np.random.default_rng(a.seed+622);order=[];batches=hashlib.sha256();hist=[];start=perf_counter()
    batch=32;ids=torch.arange(batch,device=dev)
    for step in range(1024):
        if not order:order=list(rng.permutation(len(ts)))
        t=ts[order.pop()];d=panels[t['id']];ix=rng.integers(len(d['a']),size=batch);sites=rng.integers(16,size=batch)
        batches.update(t['id'].encode());batches.update(ix.tobytes());batches.update(sites.tobytes())
        site=torch.as_tensor(sites,device=dev)
        edges=torch.full((2*batch,16),-1,device=dev,dtype=torch.int32)
        edges[ids,site]=1;edges[ids+batch,site]=0
        inputs=transfer(d,np.tile(ix,2),dev);opt.zero_grad(set_to_none=True)
        st,tok,rel=m(*inputs,tables[t['id']],gate_override=edges.reshape(-1,2,8))
        target=[torch.as_tensor(d[k][np.tile(ix,2)],device=dev,dtype=torch.long) for k in ('target1','target2')]
        rew,u=utility(st,target,price);delta=(u[:batch]-u[batch:]).detach()
        logits=torch.cat([v['gate_logits'] for v in st],dim=1)[ids,site]
        y=(delta>=0).float();w=delta.abs()+1/64
        loss=(w*F.binary_cross_entropy_with_logits(logits,y,reduction='none')).mean()/w.mean()
        loss.backward();torch.nn.utils.clip_grad_norm_(m.gates.parameters(),1.0);opt.step()
        if step in (0,1023):
            trace=dict(template=t['id'],indices=ix,sites=sites,price=price,delta=delta.cpu().numpy())
            for name,sl in [('open',slice(0,batch)),('closed',slice(batch,None))]:
                trace.update({f'{name}_{i}_{k}':v[k][sl].detach().cpu().numpy() for i,v in enumerate(st) for k in ('active','pointers','rows','gate_open')})
                trace[name+'_token']=tok[sl].detach().cpu().numpy();trace[name+'_reward']=rew[sl].detach().cpu().numpy();trace[name+'_utility']=u[sl].detach().cpu().numpy()
            np.savez_compressed(out/f'sampled-{step+1}.npz',**trace)
        if step%256==0 or step==1023:
            item=dict(step=step+1,loss=loss.item(),mean_abs_delta=delta.abs().mean().item(),positive=(delta>0).float().mean().item(),seconds=perf_counter()-start)
            if not np.isfinite(item['loss']):raise ValueError(item)
            hist.append(item);print(item,flush=True)
    assert actor_init==state_digest(m.actor.state_dict())
    torch.save(m.gates.state_dict(),out/'gates.pt')
    fit=dict(arm=a.arm,seed=a.seed,price=price,steps=1024,batch=32,rollouts=65536,lr=.002,gate_init=init,actor_state_sha256=actor_init,
             gates_sha256=digest(out/'gates.pt'),parent_sha256=meta['model_sha256'],history=hist,data_order=batches.hexdigest(),
             train_sha256={k:array_digest(v) for k,v in panels.items()},test_manifest_sha256=digest(frozen),
             gate_parameters=sum(p.numel() for p in m.gates.parameters()),seconds=perf_counter()-start,torch=torch.__version__)
    (out/'fit.json').write_text(json.dumps(fit,indent=2)+'\n')

if __name__=='__main__':main()
