"""Place the identical whole-pass generation network on CPU or MPS, then use the same Metal verifier."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns

import numpy as np
import torch

GPU=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(GPU/'whole-pass-generation'))
from adapter import specialize
from policy import Policy,packet
sys.path.insert(0,str(GPU/'recurrent-generator'))
from capture import inputs,verify
from feedback_study import bind_session


class Generation:
    def __init__(self,plan,checkpoint,device):
        self.device=device
        self.net=Policy(checkpoint['tables'],checkpoint['rules']).to(device)
        self.net.load_state_dict(checkpoint['state'])
        self.net.eval()
        self.roots=torch.as_tensor(plan['root_x'],device=device)
        self.features=torch.as_tensor(plan['child_x'],device=device)
        self.candidates=torch.as_tensor(plan['candidates'],device=device,dtype=torch.int32)
        self.catalog=self.candidates.to('mps')
        self.universal=torch.as_tensor(plan['projections'],device='mps',dtype=torch.int32)[self.catalog[:,2].long()]>=0
        self.root_ids=torch.tensor(plan['roots'],dtype=torch.int32,device='mps')

    def forward(self):
        return self.net(self.roots,self.features,self.candidates)

    def generate(self):
        latent,scores=self.forward()
        tokens=torch.cat([(scores>=0).int()[:,None],self.candidates[:,:4]],1).contiguous()
        return latent,tokens

    def seal(self,tokens):
        # All placements check their generated envelopes against the same resident device catalog.
        valid=(tokens[:,1:5]==self.catalog[:,:4]).all(1)
        proof=torch.where(valid,((tokens[:,0]!=0)&self.universal).int(),-1)
        return torch.cat([tokens,proof[:,None]],1).contiguous()

    def emit(self):
        latent,tokens=self.generate()
        return self.root_ids,self.seal(tokens.to('mps')),latent


class MetalGeneration(Generation):
    """Same checkpoint and tensor shapes as the PyTorch module, in two compiled kernels."""
    def __init__(self,plan,checkpoint):
        super().__init__(plan,checkpoint,'mps')
        self.shader=torch.mps.compile_shader((Path(__file__).parent/'forest_forward.metal').read_text())
        self.hidden=torch.empty(len(self.roots),12,dtype=torch.float32,device='mps')
        self.scores=torch.empty(len(self.candidates),dtype=torch.float32,device='mps')

    def forward(self):
        net=self.net
        self.shader.root_latents(self.roots,net.root.weight,net.root.bias,self.hidden,threads=self.hidden.numel())
        self.shader.child_scores(self.hidden,self.features,self.candidates,net.table.weight,net.consumer.weight,
                                 net.child[0].weight,net.child[0].bias,net.child[2].weight,net.child[2].bias,
                                 self.scores,threads=32*len(self.candidates),group_size=32)
        return self.hidden,self.scores


def measure(fn,uses_gpu,samples):
    results=[]
    for _ in range(4):
        fn()
    if uses_gpu:torch.mps.synchronize()
    for _ in range(samples):
        start=perf_counter_ns()
        fn()
        if uses_gpu:torch.mps.synchronize()
        results.append((perf_counter_ns()-start)/1e3)
    return dict(median_us=median(results),p10_us=float(np.percentile(results,10)),p90_us=float(np.percentile(results,90)))


def micro(profile,count):
    gpu=profile.device=='mps'
    _,tokens=profile.generate()
    device_tokens=tokens.to('mps')
    return dict(network=measure(profile.forward,gpu,count),generated_tokens=measure(profile.generate,gpu,count),
                upload=None if gpu else measure(lambda:tokens.to('mps'),True,count),
                device_check=measure(lambda:profile.seal(device_tokens),True,count),
                ready_for_verifier=measure(profile.emit,True,count))


def audit_trial(buf,truth):
    state=buf['state'].cpu().tolist()
    assert state[7] and not state[5]
    for k,idx in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
        got,want=buf[k][:state[idx]].cpu().numpy(),truth[k]
        if k=='rhs':
            np.testing.assert_array_equal(got[:,:2],want[:,:2])
            got,want=got[:,4:],want[:,4:]
        np.testing.assert_array_equal(got,want)


def study(args):
    torch.set_num_interop_threads(1)
    args.out.mkdir(parents=True,exist_ok=False)
    report={};models={}
    for seed in args.seeds:
        models[seed]=torch.load(args.weights/f'policy-{seed}.pt',weights_only=True,map_location='cpu')
    placements={'mps':1,'cpu-1':1,'cpu-4':4,'cpu-12':12,'resident-replay':1}
    if args.fused:placements={'mps':1,'cpu-1':1,'metal-compiled':1}
    for case in args.cases:
        image,program,gold=inputs(args.corpus,args.ref,case)
        plan=packet(image,program)
        with np.load(gold/'output.npz') as z:truth={k:z[k] for k in ('runs','rhs','writes','resumes')}
        for seed,checkpoint in models.items():
            summary={};sessions={};baseline=None
            for arm,threads in placements.items():
                torch.set_num_threads(threads)
                if arm=='resident-replay':
                    assert baseline is not None
                    emit=lambda:sealed
                    item={'replay':True}
                else:
                    device='cpu' if arm.startswith('cpu') else 'mps'
                    profile=MetalGeneration(plan,checkpoint) if arm=='metal-compiled' else Generation(plan,checkpoint,device)
                    emit=profile.emit
                    latent,score=profile.forward()
                    token=emit()[1]
                    if arm=='mps':
                        baseline=(latent.cpu().numpy(),score.cpu().numpy(),token.cpu().numpy())
                        sealed=emit()
                    delta=np.max(np.abs(latent.cpu().numpy()-baseline[0]))
                    changes=int(np.any(token.cpu().numpy()!=baseline[2],axis=-1).sum())
                    item=dict(replay=False,threads=threads,params=sum(p.numel() for p in profile.net.parameters()),
                              candidates=len(score),emitted=int(token[:,0].sum().item()),
                              cpu_to_gpu_token_bytes=0 if device=='mps' else int(len(score)*5*4),
                              token_differences=changes,max_latent_delta=float(delta),
                              max_score_delta=float(np.max(np.abs(score.cpu().numpy()-baseline[1]))),
                              micro=micro(profile,args.micro))
                folder=args.out/f'{case}-{seed}-{arm}'
                executor=specialize(plan,emit,True,events=True)
                executor(image/'device.json',args.reader,args.ref/'ports-1703.pt',2048,2,folder,
                         measure_resident=bind_session(sessions,arm))
                verify(folder,gold,image)
                with np.load(folder/'forest.npz') as z:
                    origins=z['children'][:,2]
                    if arm=='mps':ref_origins=origins.copy()
                    item.update(neural_rhs=int((origins>0).sum()),changed_winner_ordinals=int((origins!=ref_origins).sum()),
                                static_roots=int((z['roots'][:,2]>0).sum()),source_rhs=len(truth['rhs']))
                item['ms']=[];summary[arm]=item
            order=list(placements)
            for trial in range(2*len(order)):
                seq=order[trial%len(order):]+order[:trial%len(order)]
                for arm in (seq if trial<len(order) else seq[::-1]):
                    torch.set_num_threads(placements[arm])
                    reset,infer,buf=sessions[arm];reset();torch.mps.synchronize()
                    start=perf_counter_ns();infer();torch.mps.synchronize()
                    summary[arm]['ms'].append((perf_counter_ns()-start)/1e6)
                    audit_trial(buf,truth)
            for arm,item in summary.items():
                item['median_ms']=median(item['ms'])
                item['paired_ms_vs_mps']=list(np.subtract(item['ms'],summary['mps']['ms']))
            report[f'{case}/{seed}']=summary
            (args.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
            print(case,seed,[(k,round(v['median_ms'],1),round(v.get('micro',{}).get('network',{}).get('median_us',0))) for k,v in summary.items()],flush=True)
            sessions.clear()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','weights','out'):p.add_argument(k,type=Path)
    p.add_argument('--fused',action='store_true')
    p.add_argument('--micro',type=int,default=80)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    with torch.inference_mode():study(p.parse_args())
