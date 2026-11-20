"""Seal identical static candidate slots on CPU or Metal, then choose a verifier location."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter_ns
import torch

GPU=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(GPU/'whole-pass-generation'))
from policy import packet,Policy


class Generator:
    def __init__(self,program,image,checkpoint,device):
        p=self.plan=packet(image,program)
        self.digest=hashlib.sha256(program.read_bytes()).hexdigest()
        self.net=Policy(checkpoint['tables'],checkpoint['rules']).to(device);self.net.load_state_dict(checkpoint['state']);self.net.eval()
        self.x=torch.as_tensor(p['root_x'],device=device);self.y=torch.as_tensor(p['child_x'],device=device)
        self.c=torch.as_tensor(p['candidates'],dtype=torch.int32,device=device)
        self.root=torch.as_tensor(p['roots'],dtype=torch.int32,device=device)
        self.universal=torch.as_tensor(p['projections'],dtype=torch.int32,device=device)[self.c[:,2].long()]>=0
        self.catalog=p['candidates'][:,:4].tolist()
        self.device=device

    def emit(self,arm='learned'):
        root_latent,score=self.net(self.x,self.y,self.c);active=score>=0
        if arm=='none':active=torch.zeros_like(active)
        if arm=='all':active=torch.ones_like(active)
        parent=self.c[:,0]
        if arm=='wrong-parent':parent=(parent+1)%len(self.plan['roots'])
        tokens=torch.stack((active.int(),parent,self.c[:,1],self.c[:,2],self.c[:,3]),1).contiguous()
        valid=(tokens[:,1:]==self.c[:,:4]).all(dim=1)
        proof=torch.where(valid,(active & self.universal).int(),-1)
        return self.root,torch.cat((tokens,proof[:,None]),1).contiguous(),root_latent

    def transfer(self,dest,arm='learned'):
        start=perf_counter_ns()
        roots,child,_=self.emit(arm)
        # A GPU producer must really complete its forward and transfer all certificate words to host.
        sealed=child.cpu().numpy()
        root_ids=roots.cpu().tolist()
        after=perf_counter_ns()
        payload=dict(schema='eggfuse.sealed-forest/v1',program_sha256=self.digest,roots=root_ids,
                     catalog=self.catalog,children=sealed.tolist())
        dest.write_text(json.dumps(payload,separators=(',',':')))
        return dict(emit_and_readback_ms=(after-start)/1e6,encode_ms=(perf_counter_ns()-after)/1e6,
                    sha256=hashlib.sha256(sealed.tobytes()).hexdigest(),active=int(sealed[:,0].sum()),bytes=sealed.nbytes)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('program','image','weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--device',choices=('cpu','mps'),default='cpu')
    p.add_argument('--arm',choices=('learned','all','none','wrong-parent'),default='learned')
    a=p.parse_args()
    with torch.inference_mode():
        g=Generator(a.program,a.image,torch.load(a.weights,weights_only=True,map_location='cpu'),a.device);print(g.transfer(a.out,a.arm))
