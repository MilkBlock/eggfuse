"""Train the shared hashed-port pointer head without Pass 3 data or rule IDs."""
import argparse
import json
from pathlib import Path

import torch
import torch.nn.functional as F

BUCKETS, DIM = 128, 8

def train(dest):
    torch.set_num_threads(1)
    torch.manual_seed(1703)
    embedding = torch.nn.Embedding(BUCKETS,DIM)
    null = torch.nn.Parameter(torch.tensor(0.5))
    optimizer = torch.optim.Adam([embedding.weight,null],lr=0.01)
    for step in range(800):
        width = 1 + step % 4
        candidates = torch.randint(4096,(64,16,width))
        queries = candidates[:,0].clone()
        # Include close negatives and actual empty keys.
        candidates[:,1:5,:-1] = queries[:,None,:-1]
        queries[32:] = torch.randint(4096,(32,width))
        target = (candidates==queries[:,None]).all(-1)
        labels = torch.where(target.any(-1),target.long().argmax(-1),16)
        e = F.normalize(embedding.weight,dim=-1)
        score = (e[queries%BUCKETS][:,None]*e[candidates%BUCKETS]).sum(-1).mean(-1)
        loss = F.cross_entropy(torch.cat([score,null.expand(64,1)],1)*16,labels)
        optimizer.zero_grad(); loss.backward(); optimizer.step()
    dest.write_text(json.dumps(dict(schema='port-pointer/v1',seed=1703,buckets=BUCKETS,dim=DIM,
        null=null.item(),embedding=F.normalize(embedding.weight.detach(),dim=-1).tolist()),separators=(',',':'))+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    train(parser.parse_args().destination)
