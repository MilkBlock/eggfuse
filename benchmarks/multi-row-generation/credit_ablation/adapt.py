"""Adapt a frozen single-row checkpoint at width two with three supervision choices."""
import argparse
import json
from pathlib import Path
import hashlib
import time

import numpy as np
import torch
from torch.nn import functional as F

from credit_inputs import WIDTH, SEEDS, templates, dataset, array_digest
from actor import sample_rollout, CentralCritic
from width_ablation.model import WidthSystem
from fit import EClassSchema, align, device, transfer, objective, digest, state_digest
from reward import team_reward


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('root',type=Path);parser.add_argument('width_root',type=Path)
    parser.add_argument('arm',choices=('supervised','supervised1','team','counterfactual'));parser.add_argument('seed',type=int,choices=SEEDS)
    a=parser.parse_args();out=a.root/f'{a.arm}-{a.seed}';out.mkdir(parents=True,exist_ok=True)
    if (out/'final.pt').exists():raise FileExistsError(out)
    if not (a.root/'fresh-credit-inputs.json').is_file():raise FileNotFoundError('freeze the evaluation inputs before fitting')
    dev=device();ts=[t for t in templates() if t['split']=='train'];schema=EClassSchema(ts)
    parent=a.width_root/str(a.seed);source=json.loads((parent/'fit.json').read_text())
    assert digest(parent/'final.pt')==source['model_sha256']
    model=WidthSystem(schema,a.seed);model.load_state_dict(torch.load(parent/'final.pt',map_location='cpu',weights_only=True));model.to(dev).train()
    optimizer=torch.optim.Adam(model.parameters(),lr=.0003)
    training={t['id']:dataset('train',t) for t in ts};banks={t['id']:schema.bank(t,'pairwise',dev) for t in ts}
    assert {k:array_digest(v) for k,v in training.items()}==source['source']
    rl=a.arm in ('team','counterfactual');critic_hash=None;critic_parameters=0
    if rl:
        torch.manual_seed(a.seed+221)
        critic=CentralCritic(32);critic_hash=state_digest(critic.state_dict());critic_parameters=sum(v.numel() for v in critic.parameters())
        critic.to(dev).train();copt=torch.optim.Adam(critic.parameters(),lr=.001)
    torch.manual_seed(a.seed+537)
    rng=np.random.default_rng(a.seed+537);order=[];batch_hash=hashlib.sha256();history=[];start=time.perf_counter()
    reward_parts=('C1','C2','P','E2','W1','W2')
    for step in range(1024):
        if not order:order=list(rng.permutation(len(ts)))
        t=ts[order.pop()];d=training[t['id']];ix=rng.integers(len(d['a']),size=32)
        batch_hash.update(t['id'].encode());batch_hash.update(ix.tobytes())
        optimizer.zero_grad(set_to_none=True);table=model.encoder.encode_bank(banks[t['id']])
        inputs=transfer(d,ix,dev);info={}
        if rl:
            copt.zero_grad(set_to_none=True)
            stages,token,relations,recs=sample_rollout(model,inputs,table,epsilon=.04)
            y1,y2=[torch.as_tensor(d[k][ix],device=dev,dtype=torch.long) for k in ('target1','target2')]
            reward,parts=team_reward(*stages,y1,y2)
            q,team,cf=critic(recs)
            baseline=(cf if a.arm=='counterfactual' else team).detach()
            adv=reward[:,None,None]-baseline
            logp=torch.stack([r.log_prob for r in recs],dim=1)
            entropy=torch.stack([r.entropy for r in recs],dim=1)
            loss=-(adv*logp).mean()-.003*entropy.mean()
            critic_loss=F.mse_loss(q,reward[:,None].expand_as(q))
            critic_loss.backward();torch.nn.utils.clip_grad_norm_(critic.parameters(),1.0);copt.step()
            if step%256==0 or step==1023:
                info=dict(reward=reward.mean().item(),critic_mse=critic_loss.item(),entropy=entropy.mean().item(),
                          advantage_std=adv.std().item(),team_minus_cf_abs=(team-cf).detach().abs().mean().item(),
                          **{k:parts[k].mean().item() for k in reward_parts})
        else:
            stages,token,relations=model(*inputs,table,rows=1 if a.arm=='supervised1' else 2)
            label=align(stages,d['target1'][ix],d['target2'][ix])
            targets=[torch.as_tensor(v,device=dev,dtype=torch.long) for v in label]
            loss=objective(model,stages,relations,targets,torch.as_tensor(d['request_legal'][ix],device=dev,dtype=torch.long))
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        if rl and step in (0,1023):
            trace={f'{s}_{k}':v[k].detach().cpu().numpy() for s,v in enumerate(stages) for k in ('active','pointers','rows')}
            trace.update(template=t['id'],indices=ix,token=token.detach().cpu().numpy(),reward=reward.cpu().numpy(),
                         **{k:parts[k].cpu().numpy() for k in reward_parts})
            np.savez_compressed(out/f'sampled-{step+1}.npz',**trace)
        if step%256==0 or step==1023:
            item=dict(step=step+1,loss=float(loss.detach()),seconds=time.perf_counter()-start,**info)
            if not all(np.isfinite(x) for x in item.values()):raise ValueError(item)
            print(item,flush=True);history.append(item)
    torch.save(model.state_dict(),out/'final.pt')
    if rl:torch.save(critic.state_dict(),out/'critic.pt')
    meta=dict(arm=a.arm,seed=a.seed,parent_sha256=source['model_sha256'],model_sha256=digest(out/'final.pt'),steps=1024,batch=32,
              graph_rollouts=32768,sampled_joint_steps=32*1024*8 if rl else 0,actor_lr=.0003,critic_lr=.001 if rl else None,
              critic_init=critic_hash,critic_parameters=critic_parameters,data_order=batch_hash.hexdigest(),history=history,
              seconds=time.perf_counter()-start,test_manifest_sha256=digest(a.root/'fresh-credit-inputs.json'))
    (out/'fit.json').write_text(json.dumps(meta,indent=2)+'\n')

if __name__=='__main__':main()
