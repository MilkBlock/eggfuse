"""Generate the complete static-root proof forest first, then validate it against the actual Pass 3 source schedule."""
import argparse
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns

import numpy as np
import torch

from adapter import specialize,run
from policy import Policy, packet, read
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'recurrent-generator'))
from capture import inputs,verify


def open_generator(p,checkpoint,arm):
    device='mps'
    net=Policy(checkpoint['tables'],checkpoint['rules']).to(device)
    net.load_state_dict(checkpoint['state']);net.eval()
    x=torch.as_tensor(p['root_x'],device=device);y=torch.as_tensor(p['child_x'],device=device)
    candidates=torch.as_tensor(p['candidates'],dtype=torch.int32,device=device)
    root_ids=torch.tensor(p['roots'],dtype=torch.int32,device=device)
    universal=torch.as_tensor(p['projections'],dtype=torch.int32,device=device)[candidates[:,2].long()]>=0
    saved=[]
    def emit():
        root,score=net(x,y,candidates)
        active=score>=0
        if arm=='none':active=torch.zeros_like(active)
        if arm=='all':active=torch.ones_like(active)
        parent=candidates[:,0]
        if arm=='wrong-parent':parent=(parent+1)%len(p['roots'])
        token=torch.stack([active.int(),parent,candidates[:,1],candidates[:,2],candidates[:,3]],1).contiguous()
        # Check all proof envelopes against the static typed catalog in a single GPU tensor pass.
        # This consumes the already generated entire forest and checks no current or future source graph.
        valid_ref=(token[:,1]==candidates[:,0]) & (token[:,2]==candidates[:,1]) & (token[:,3]==candidates[:,2]) & (token[:,4]==candidates[:,3])
        prechecked=active & valid_ref & universal
        if arm=='point':prechecked=torch.zeros_like(prechecked)
        proof=torch.where(valid_ref,prechecked.int(),-1)
        if arm=='proof-only':
            # Preserve all raw proposals. This verifier declines claims that need any additional LHS matching.
            proof=torch.where(active & valid_ref & ~universal,-2,proof)
        token=torch.cat([token,proof[:,None]],1).contiguous()
        saved[:]=[token,root]
        return root_ids,token,root
    return emit,saved


def audit(folder,source,p,policy_tokens,residual):
    roles=read(folder/'run.json')['execution_roles']
    with np.load(folder/'forest.npz') as z,np.load(folder/'output.npz') as g:
        root,child,ports=z['roots'],z['children'],z['outputs']
        rhs=g['rhs'];ordinals=root[:,2].tolist()+child[:,2].tolist()
        valid=[e for e in ordinals if e>0];assert len(valid)==len(set(valid))
        for j,r in enumerate(p['roots']):
            if root[j,2]:assert rhs[root[j,2]-1,1]==r
        examples=[]
        for idx in np.flatnonzero(child[:,2]):
            parent,e,r,pivot,_,_,portmap=p['candidates'][idx]
            _,issued,pred_port,rule,entry,_=policy_tokens[idx].tolist()
            assert policy_tokens[idx,0] and (parent,e,r,pivot)==(issued,pred_port,rule,entry)
            parent_ordinal,row,ticket=ports[portmap]
            assert parent_ordinal>0 and parent_ordinal==root[parent,2]
            accept_run,_,ordinal,observed_row,observed_ticket,*_=child[idx]
            assert row==observed_row and ticket==observed_ticket and rhs[ordinal-1,3]==row
            assert rhs[ordinal-1,0]==accept_run and rhs[ordinal-1,1]==r
            assert rhs[parent_ordinal-1,0]<accept_run
            if len(examples)<3:examples.append(dict(parent_rhs=int(parent_ordinal),parent_rule=int(p['roots'][parent]),
                effect=int(e),rule=int(r),pivot=int(pivot),row=int(row),ticket=int(ticket),rhs=int(ordinal),run=int(accept_run)))
        with np.load(source/'output.npz') as official:
            total=len(official['rhs']);canonical=official['runs']
            first=next((i+1 for i,(x,y) in enumerate(zip(g['runs'],canonical)) if np.any(x!=y)),None)
            if first is None and len(g['runs'])!=len(canonical):first=min(len(g['runs']),len(canonical))+1
        assert first is None if residual else first is not None
        return dict(candidates=len(child),proposals=int(policy_tokens[:,0].sum()),static_roots=int((root[:,2]>0).sum()),
                    global_projection_proofs=int((policy_tokens[:,5]>0).sum()),projection_rhs=int(((child[:,2]>0)&(policy_tokens[:,5]>0)).sum()),
                    child_winners=int((child[:,2]>0).sum()),point_route_attempts=int(child[:,5].sum()),
                    rejected_bad_pointer=int((child[:,7]!=0).sum()),covered_runs=int(len(set(child[child[:,2]>0,0]))),
                    open_or_unsuccessful=int(policy_tokens[:,0].sum()-(child[:,2]>0).sum()),
                    exact_residual=roles['rhs_inputs_from_exact_search'],actual_rhs=len(rhs),reference_rhs=total,
                    actual_runs=len(g['runs']),source_runs=len(canonical),first_divergence=first,examples=examples)


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);summary={}
    for case in a.cases:
        image,program,source=inputs(a.corpus,a.ref,case);p=packet(image,program)
        for seed in a.seeds:
            ck=torch.load(a.weights/f'policy-{seed}.pt',weights_only=True)
            result={}
            sessions={}
            for arm in ['exact','learned','point','none','wrong-parent','all','no-residual']:
                folder=a.out/f'{case}-{seed}-{arm}'
                emit,saved=open_generator(p,ck,arm)
                executor=run.execute if arm=='exact' else specialize(p,emit,arm!='no-residual')
                timed=arm in ('learned','exact','point','all')
                def bind(infer,buf,*_):
                    original={k:buf[k].clone() for k in ('state','meta','head','dyn','wm')}
                    def reset():
                        for k,t in original.items():buf[k].copy_(t)
                        for k in ('regs','count','rhs','runs','writes','resumes'):buf[k].zero_()
                    sessions[arm]=(reset,infer,buf)
                executor(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,folder,measure_resident=bind if timed else None)
                if arm!='no-residual':verify(folder,source,image)
                if arm!='exact':
                    tokens=saved[0].cpu().numpy()
                    result[arm]=audit(folder,source,p,tokens,arm!='no-residual')
                    if arm=='learned':reference_tokens=tokens.copy()
                    if arm=='point':
                        np.testing.assert_array_equal(tokens[:,:5],reference_tokens[:,:5])
                        assert result[arm]['child_winners']==result['learned']['child_winners']
                    if arm=='no-residual':np.testing.assert_array_equal(tokens,reference_tokens)
                    if arm in ('wrong-parent','none'):assert result[arm]['child_winners']==0
                else:result[arm]=dict(semantic_exact=True)
            for arm in sessions:result[arm]['ms']=[]
            order=list(sessions)
            with np.load(source/'output.npz') as z:truth={k:z[k] for k in ('rhs','runs','writes','resumes')}
            for trial in range(a.repeats):
                seq=order[trial%len(order):]+order[:trial%len(order)]
                for arm in seq:
                    reset,infer,buf=sessions[arm];reset();torch.mps.synchronize()
                    begin=perf_counter_ns();infer();torch.mps.synchronize();result[arm]['ms'].append((perf_counter_ns()-begin)/1e6)
                    st=buf['state'].cpu().tolist();assert st[7] and not st[5]
                    for k,i in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                        obs,ref=buf[k][:st[i]].cpu().numpy(),truth[k]
                        if k=='rhs':
                            np.testing.assert_array_equal(obs[:,:2],ref[:,:2]);obs,ref=obs[:,4:],ref[:,4:]
                        np.testing.assert_array_equal(obs,ref)
            for arm in sessions:result[arm]['median_ms']=median(result[arm]['ms'])
            summary[f'{case}/{seed}']=result
            (a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
            print(case,seed,result['learned'],flush=True);sessions.clear()


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','ref','reader','weights','out'):ap.add_argument(name,type=Path)
    ap.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    ap.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    ap.add_argument('--repeats',type=int,default=6)
    with torch.inference_mode():study(ap.parse_args())
