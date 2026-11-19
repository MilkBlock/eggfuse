"""Frozen-actor diagnostic of reward-baseline variance for the activation bias."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from credit_inputs import fresh_panel,templates
from actor import sample_rollout,CentralCritic
from width_ablation.model import WidthSystem
from fit import device,transfer,EClassSchema
from reward import team_reward


def bias_gradient(stages,records,adv,eps):
    # The only path from the shared activation bias to each log density is the
    # active Bernoulli factor: sampled actions in future history are detached.
    gradients=[]
    for s in range(2):
        scores=stages[s]['active_logits'].reshape(-1,2,4,2)
        for t in range(4):
            rec=records[4*s+t];p=scores[:,:,t].softmax(-1);act=rec.action[...,0]
            chosen=p.gather(-1,act[...,None]).squeeze(-1)
            factor=(1-eps)*chosen/((1-eps)*chosen+eps/2)
            hard=(act[...,None]==torch.arange(2,device=act.device)).to(p.dtype)
            gradients.append((hard-p)*factor[...,None]*adv[:,4*s+t,:,None])
    return torch.stack(gradients,1).mean((1,2))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args();dev=device()
    ts=templates();schema=EClassSchema([t for t in ts if t['split']=='train']);out={};K=32
    for arm in ('team','counterfactual'):
        for seed in (1703,1709):
            name=f'{arm}-{seed}';folder=args.root/name;m=WidthSystem(schema,seed)
            m.load_state_dict(torch.load(folder/'final.pt',weights_only=True,map_location='cpu'));m.to(dev).eval()
            c=CentralCritic();c.load_state_dict(torch.load(folder/'critic.pt',weights_only=True,map_location='cpu'));c.to(dev).eval()
            torch.manual_seed(seed+7011);variances=[];mses=[];diffs=[];errors=[];all_reward=[]
            for t in ts:
                if t['split']!='heldout':continue
                d=fresh_panel(t);bank=schema.bank(t,'pairwise',dev)
                with torch.no_grad():table=m.encoder.encode_bank(bank)
                # Two complete raw groups spanning blind and targeted, all four phases and both origin variants.
                for source_index in range(16):
                    ix=np.full(K,source_index,dtype=np.int64)
                    enable_grad=not errors
                    with torch.set_grad_enabled(enable_grad):
                        stages,token,relations,recs=sample_rollout(m,transfer(d,ix,dev),table,epsilon=.04)
                        reward,_=team_reward(*stages,*[torch.as_tensor(d[k][ix],device=dev) for k in ('target1','target2')])
                        q,both,conditional=c(recs)
                        g=[]
                        for baseline in (both,conditional):
                            adv=(reward[:,None,None]-baseline).detach()
                            gb=bias_gradient(stages,recs,adv,.04)
                            if enable_grad:
                                log=torch.stack([v.log_prob for v in recs],1)
                                direct,=torch.autograd.grad((log*adv).mean(),m.decoder.active.bias,retain_graph=True)
                                err=(direct-gb.mean(0)).abs().max().item()
                                torch.testing.assert_close(direct,gb.mean(0),atol=2e-6,rtol=1e-4);errors.append(err)
                            g.append(gb.detach().cpu().numpy())
                    variances.append([float(v.var(0,ddof=1).sum()) for v in g])
                    diffs.append(float((both-conditional).detach().abs().mean()))
                    mses.append(float(((q.detach()-reward[:,None])**2).mean()))
                    all_reward.append(float(reward.mean()))
            v=np.array(variances)
            out[name]=dict(sources=len(v),rollouts_per_source=K,team_gradient_variance=float(v[:,0].mean()),
                           conditional_gradient_variance=float(v[:,1].mean()),ratio_of_means=float(v[:,1].mean()/v[:,0].mean()),
                           conditional_lower_sources=int((v[:,1]<v[:,0]).sum()),mean_abs_baseline_difference=float(np.mean(diffs)),
                           mean_q_mse=float(np.mean(mses)),mean_sample_reward=float(np.mean(all_reward)),autograd_check_max_error=max(errors))
            print(name,out[name],flush=True)
    (args.root/'baseline-variance.json').write_text(json.dumps(out,indent=2)+'\n')

if __name__=='__main__':main()
