"""Train a bounded page selector on random multi-entry equality joins only."""
import argparse
import json
from pathlib import Path

import torch


def train(args):
    torch.manual_seed(args.seed)
    generator=torch.Generator().manual_seed(args.seed)
    model=torch.nn.Linear(6,1,bias=False).to(args.device)
    optimizer=torch.optim.Adam(model.parameters(),lr=.025)
    for step in range(240):
        # Per-example dictionaries include decoys, collisions and repeated keys.
        code=torch.randint(64,(64,64,3),generator=generator)
        rows=torch.randint(64,(64,8,8),generator=generator)
        query=rows[:,0,0]
        indices=torch.arange(64)
        q=code[indices,query][:,None,None,:]
        keys=code[indices[:,None,None],rows]
        hit=(keys==q).any(2).float()
        sorted_keys=keys.sort(dim=2).values
        distinct=1+(sorted_keys[:,:,1:]!=sorted_keys[:,:,:-1]).sum(2)
        x=torch.cat((hit,hit*(1-distinct/8)),dim=-1).to(args.device)
        labels=(rows==query[:,None,None]).any(2).float().to(args.device)
        # Give every page containing an answer credit, including non-first pages.
        logits=model(x).squeeze(-1)
        loss=-(labels*logits.log_softmax(dim=-1)).sum(1).div(labels.sum(1)).mean()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    root=torch.nn.Linear(3,1,bias=False).to(args.device)
    root_optimizer=torch.optim.Adam(root.parameters(),lr=.03)
    for _ in range(160):
        # Seminaive eligibility depends on either the parent epoch or a fresh
        # suffix witness. Only page epochs and the current watermark are visible.
        epoch=torch.randint(0,33,(64,64),generator=generator).sort(1).values.reshape(64,8,8)
        wm=torch.randint(0,33,(64,1),generator=generator)
        suffix=torch.randint(0,33,epoch.shape,generator=generator)
        active=torch.rand(epoch.shape,generator=generator)<.12
        correct=active & (torch.maximum(epoch,suffix)>=wm[:,:,None])
        labels=correct.sum(2).float().to(args.device)
        hi,lo=epoch[:,:,-1],epoch[:,:,0]
        features=torch.stack(((hi>=wm).float(),(lo>=wm).float(),hi.float()/32),-1).to(args.device)
        loss=-(labels*root(features).squeeze(-1).log_softmax(dim=-1)).sum(1).div(labels.sum(1).clamp_min(1)).mean()
        root_optimizer.zero_grad()
        loss.backward()
        root_optimizer.step()
    root_weights=root.weight.detach().cpu().flatten().tolist()
    args.out.write_text(json.dumps(dict(seed=args.seed,device=args.device,steps=step+1,
        root_weights=root_weights,weights=model.weight.detach().cpu().flatten().tolist()),indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path)
    parser.add_argument('--device',choices=('cpu','mps'),default='mps')
    parser.add_argument('--seed',type=int,default=1703)
    train(parser.parse_args())
