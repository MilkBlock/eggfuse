"""Open-loop GPU token generation for the input-closed attribute domain, followed by one independent check."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from certificate import compile_domain, generate_reference_proposal, require
from study import audit_prefix

WIDTH = 24
SYMBOLS = 8192
BUDGET = 24


class Pointer(nn.Module):
    def __init__(self):
        super().__init__()
        gen=torch.Generator().manual_seed(2251)
        self.register_buffer('codes',F.normalize(torch.randn(SYMBOLS,WIDTH,generator=gen),dim=-1))
        self.query=nn.Linear(WIDTH,WIDTH,bias=False)
        self.key=nn.Linear(WIDTH,WIDTH,bias=False)
        self.gate=nn.Sequential(nn.Linear(3,8),nn.Tanh(),nn.Linear(8,1))

    def pointers(self,domain):
        classes=self.codes[domain[:,0]]
        tails=self.codes[domain[:,1].clamp_min(0)]
        scores=12.0*(F.normalize(self.query(tails),dim=-1)@F.normalize(self.key(classes),dim=-1).T)
        return scores

    def initial(self,domain):
        return torch.zeros((len(domain),5),device=domain.device,dtype=torch.int64)

    def propose(self,domain,score,prev,seed_value,increment,mask_history=False,rotate=False):
        root=domain[:,1]<0
        best,choice=score.max(1)
        if rotate:choice=(choice+1)%len(domain)
        earlier=prev[choice]
        if mask_history:earlier=torch.zeros_like(earlier)
        gate=self.gate(torch.stack([root.float(),earlier[:,0].float(),best/12],1)).squeeze(1)
        activate=(gate>0) & (prev[:,0]==0)
        zeros=torch.zeros_like(choice)
        # The chosen parent's actual prior token supplies both fields. Source
        # identities and the compiled recurrence are exact projections.
        candidate=torch.stack([torch.ones_like(choice),domain[:,0],
                               torch.where(root,zeros-1,choice),
                               torch.where(root,zeros,earlier[:,3]+1),
                               torch.where(root,zeros+seed_value,earlier[:,4]+increment)],1)
        return torch.where(activate[:,None],candidate,prev),gate


def load_case(path):
    packet=json.loads(path.read_bytes())
    p,d,edges,writes,build=compile_domain(packet)
    require(max(d[:,0])<SYMBOLS,'input symbol codebook exhausted')
    return (packet,p,d,edges,writes,build)


def permute_training_domain(domain,claims,rng):
    n=len(domain)
    # No stable row position or class code is shared by two training draws.
    ix=rng.permutation(n)
    classes=rng.choice(SYMBOLS-1,n,replace=False)+1
    rename=dict(zip(map(int,domain[:,0]),map(int,classes)))
    inverse=np.argsort(ix)
    d=np.array([(rename[int(c)],-1 if t<0 else rename[int(t)]) for c,t in domain[ix]],dtype=np.int64)
    parent=np.array([-1 if x<0 else inverse[x] for x in claims[ix,2]],dtype=np.int64)
    return torch.tensor(d),torch.tensor(parent)


def train(model,cases,updates,seed):
    rng=np.random.default_rng(seed)
    opt=torch.optim.Adam(model.parameters(),lr=.015)
    curves=[]
    for step in range(updates):
        p,domain,claims=cases[step%len(cases)]
        d,expected=permute_training_domain(domain,claims,rng)
        scores=model.pointers(d)
        nonroot=expected>=0
        loss=F.cross_entropy(scores[nonroot],expected[nonroot])
        state=model.initial(d)
        # The training rollout consumes its own emitted history as well.
        for _ in range(9):
            parent_ready=state[expected.clamp_min(0),0].bool()
            ready=(~nonroot)|parent_ready
            nxt,gate=model.propose(d,scores,state,p.initial_value,p.increment)
            loss=loss+.16*F.binary_cross_entropy_with_logits(gate,ready.float())
            state=nxt.detach()
        opt.zero_grad();loss.backward();opt.step()
        if step%50==0:curves.append(float(loss.detach()))
    return curves


def generate(model,domain,plan,control):
    scores=model.pointers(domain)
    state=model.initial(domain)
    for _ in range(BUDGET):
        state,_=model.propose(domain,scores,state,plan.initial_value,plan.increment,
                              mask_history=control=='zero-parent-token',rotate=control=='rotate-parent')
    return state


def benchmark(model,shader,case,gold,reps):
    packet,plan,domain,members,writes,_=case
    graph=torch.tensor(domain,device='mps')
    config=torch.tensor([len(domain),plan.initial_value,plan.increment],device='mps')
    flags=torch.empty((len(domain),2),dtype=torch.int32,device='mps')
    result={}
    for control in ('intact','permuted-rows','zero-parent-token','rotate-parent'):
        # A coordinate change only; all rows, references and classes move together.
        order=np.random.default_rng(5013).permutation(len(domain)) if control=='permuted-rows' else np.arange(len(domain))
        perm=torch.tensor(order,device='mps')
        inverse=torch.tensor(np.argsort(order),device='mps')
        model_input=graph[perm] if control=='permuted-rows' else graph
        latency=[]
        for _ in range(reps if control=='intact' else 1):
            torch.mps.synchronize()
            start=perf_counter_ns()
            token=generate(model,model_input,plan,control)
            if control=='permuted-rows':
                token=token[inverse]
                parent=token[:,2]
                token[:,2]=torch.where(parent>=0,perm[parent.clamp_min(0)],parent)
            shader.certify(graph,token,config,flags,threads=len(domain))
            torch.mps.synchronize()
            latency.append((perf_counter_ns()-start)/1e6)
        # CPU inspection begins only after generation AND the one GPU check.
        observed=token.cpu().numpy()
        illegal,missing=flags.cpu().sum(0).tolist()
        complete=not (illegal or missing)
        parents=observed[1:,2]
        active=observed[1:,0].astype(bool)
        wrong_parent=sum(bool(p<0 or p>=len(domain) or domain[p,0]!=domain[i,1])
                         for i,(p,present) in enumerate(zip(parents,active),1) if present)
        details=dict(offline_initializer_rhs=1,full_pass_integrated=False,wrong_parent_among_issued=wrong_parent,issued=int(observed[:,0].sum()),illegal=illegal,uncovered=missing,
                     complete=complete,checker_dispatches=1,generator_waves=BUDGET,
                     field_copy='own identity; depth and value from selected previous parent',
                     gpu_generate_and_check_ms=latency,median_ms=median(latency))
        if control=='permuted-rows':
            details['same_tokens_after_inverse_permutation']=bool(np.array_equal(observed,result['intact']['raw_tokens']))
        if control=='intact':
            details['raw_tokens']=observed.tolist()
            details['source_domain']=domain.tolist()
        if complete:
            details['ordered_prefix_audit']=audit_prefix(gold,plan,packet,members,observed,writes)
        result[control]=details
    return result


def main(a):
    torch.set_num_threads(1)
    require(torch.backends.mps.is_available(),'MPS required')
    collection=json.loads((a.families/'collection.json').read_bytes())
    names=[name for name,row in collection.items() if row['split']=='train']
    held=[name for name,row in collection.items() if row['split']=='heldout']
    require(len(names)==4 and len(held)==2,'unexpected family split')
    training=[]
    for name in names:
        _,p,d,*_=load_case(a.families/name/'input/ingress.json')
        training.append((p,d,generate_reference_proposal(p,d)))
    shader=torch.mps.compile_shader((Path(__file__).parent/'coverage.metal').read_text())
    report=dict(torch_version=str(torch.__version__),training=names,heldout=held,training_updates=a.updates,learned={},architectural_budget=BUDGET,
                cold_setup_excluded=True)
    a.out.mkdir(parents=True,exist_ok=False)
    for seed in (1703,1709):
        torch.manual_seed(seed)
        net=Pointer()
        loss=train(net,training,a.updates,seed)
        path=a.out/f'pointer-{seed}.pt'
        torch.save(net.state_dict(),path)
        net.eval().to('mps')
        record=dict(loss_every_50=loss,weight_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    trainable_parameters=sum(x.numel() for x in net.parameters()),
                    fixed_symbol_codebook_bytes=net.codes.numel()*net.codes.element_size(),results={})
        with torch.inference_mode():
            for name in ('sum-bits','dot-product',*held):
                if name in held:
                    source=a.families/name/'input';gold=a.families/name/'device'
                else:
                    source=a.ref/f'release-input-{name}';gold=a.ref/f'release-{name}'
                result=benchmark(net,shader,load_case(source/'ingress.json'),gold,a.repetitions)
                record['results'][name]=result
                print(seed,name,[(c,r['illegal'],r['uncovered']) for c,r in result.items()],flush=True)
        report['learned'][seed]=record
        (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('ref','families','out'):parser.add_argument(k,type=Path)
    parser.add_argument('--updates',type=int,default=350)
    parser.add_argument('--repetitions',type=int,default=7)
    main(parser.parse_args())
