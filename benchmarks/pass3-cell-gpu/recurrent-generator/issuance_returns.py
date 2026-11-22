"""Two-action expected return at a prospective recursive issuance decision."""
import argparse
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import torch

from capture import execute, inputs, load_catalog, read, verify
from chain_check import serial_compiler
from compound_model import CompoundActor, compiled_actions


class Intervention:
    def __init__(self, actor, joins, tails, entries, decision, take, skip, unit):
        self.actor, self.joins, self.tails = actor, joins, tails
        self.decision, self.take, self.skip = decision, take, skip
        self.unit=unit
        self.allowed = []
        for j in range(len(joins)):
            allowed = True
            while j >= 0:
                allowed &= entries[joins[j][3]][0] >= 0
                j = tails[j]
            self.allowed.append(allowed)

    def reset(self):
        self.previous = torch.zeros(1, 2, 12)
        self.seen = 0
        self.record = None

    def emit(self, observation, run):
        idx=next((i for i,j in enumerate(self.joins) if j[0]==self.unit),0)
        leaf=self.joins[idx][1]
        candidates=observation[0,8*leaf:8*leaf+8]
        present=(candidates[:,0]>=0) & (candidates[:,4]==0) & (candidates[:,5]>0)
        eligible=self.unit is not None and self.record is None and self.allowed[idx] and bool(present.any())
        self.seen+=int(eligible)
        intervene=eligible and self.seen==self.decision
        adjustment=None
        if intervene:
            # Matched upstream exploration in both arms. The actor ranks the
            # visible addresses. No verifier status or future winner is read.
            adjustment=torch.zeros(1,2,observation.shape[1])
            adjustment[0,0,8*leaf:8*leaf+8]=present.float()*1e4
        _, roots = self.actor.root.step(observation, self.previous,score_adjust=adjustment)
        reply = torch.zeros(1, 2, 4)
        def choose(logits):
            bank = len(self.joins)
            scores = logits.clone()
            for j, allowed in enumerate(self.allowed):
                if not allowed:
                    scores[:,:,1+j::bank] = -1e4
            actions = scores.argmax(-1)
            if intervene:
                lane=1
                assert int(roots[0,0,8])==leaf+1
                action=1+idx
                prefix=next(i for i,j in enumerate(self.joins)
                            if j[1:]==self.joins[idx][1:] and self.tails[i]<0)
                alternative=0 if self.skip else 1+prefix
                self.record=(roots.numpy().copy(),lane,run,action,alternative)
                actions[0,lane]=action if self.take else alternative
            if self.unit is None and self.record is None:
                for lane in range(2):
                    action=int(scores[0,lane,1:].argmax())+1
                    if scores[0,lane,action]<-9999:
                        continue
                    self.seen+=1
                    if self.seen==self.decision:
                        self.record=(roots.numpy().copy(),lane,run,action,0)
                        actions[0,lane]=action if self.take else 0
                        break
            return actions
        _, self.previous, _ = self.actor.propose_children(roots, reply, False, torch.tensor([run]), choose)
        return torch.cat([roots,self.previous],1)[0]


def main(a):
    torch.set_num_threads(1)
    ref=a.exp/'pass3-release-reproduction-20261120'
    corpus=a.exp/'repair-bake-families-20261120'
    donor=ref/'sum-bits/program.json'
    model=read(a.checkpoint/'policy.json')
    joins,tails,wires=compiled_actions(read(donor),model['three_step'])
    actor=CompoundActor(joins,wires)
    actor.load_state_dict(torch.load(a.checkpoint/'actor.pt',weights_only=True))
    optimizer=torch.optim.Adam([actor.score,actor.row_score,actor.null],lr=a.learning_rate)
    a.out.mkdir(parents=True,exist_ok=False)
    rows=[]
    decisions=[]
    build_cache=TemporaryDirectory()
    libraries={}
    def compile_kernel(source):
        key=hashlib.sha256(source.encode()).hexdigest()
        if key not in libraries:
            build=Path(build_cache.name)/key
            build.mkdir()
            libraries[key]=serial_compiler(build)(source)
        return libraries[key]
    source_counts={}
    reference={}
    if a.birth_source:
        from fept import measure,retained
        for case in model['train']:
            image,program,gold=inputs(corpus,ref,case)
            source=a.birth_source/case
            source_counts[case]=retained(source,image)
            cfg=dict(catalog=load_catalog(image,program,donor),rows=2,hidden=8,ranks=8,waves=2,
                     weights=model['roots'],compound=dict(joins=joins,tails=tails,wires=wires,
                     child=model['child'],batch=True,named_boundary=True))
            with TemporaryDirectory() as temp:
                dest=Path(temp)/'baseline'
                execute(image/'device.json',a.exp/'rotary-axes-20261119/packed-1703/final.pt',
                        ref/'ports-1703.pt',2048,2,dest,neural=cfg,count_work=True,
                        serial_compile=compile_kernel,birth_audit=True)
                verify(dest,gold,image)
                reference[case]=measure(dest,source,source_counts[case])
        if not sum(v['issued'] for v in reference.values()):
            raise ValueError("no training proposals for the FEPT baseline")
        rho=sum(v['visible'] for v in reference.values())/sum(v['issued'] for v in reference.values())
        (a.out/'training-baseline.json').write_text(json.dumps(reference,indent=2)+'\n')
    for iteration in range(a.updates):
        case=model['train'][iteration%len(model['train'])]
        image,program,gold=inputs(corpus,ref,case)
        entries=load_catalog(image,program,donor)
        arms=[]
        records=[]
        # Select by issuance order alone, before either arm's verifier outcome.
        decision=1+iteration//len(model['three_step'])
        natural=iteration>=2*len(model['three_step'])
        unit=None if natural else model['three_step'][iteration%len(model['three_step'])]
        if natural:
            decision=1+((iteration//4)*7+iteration%4*3)%19 if a.birth_source else 1+(iteration*13)%26
        skip=natural or iteration%2==0
        with TemporaryDirectory() as temp:
            for take in (True,False):
                policy=Intervention(actor,joins,tails,entries,decision,take,skip,unit)
                dest=Path(temp)/str(take)
                cfg=dict(catalog=entries,rows=2,hidden=8,ranks=8,waves=2,weights=model['roots'],
                         compound=dict(joins=joins,tails=tails,wires=wires,child=model['child'],
                                       batch=True,named_boundary=True,host_actor=policy))
                execute(image/'device.json',a.exp/'rotary-axes-20261119/packed-1703/final.pt',
                        ref/'ports-1703.pt',2048,2,dest,neural=cfg,count_work=True,
                        serial_compile=compile_kernel,birth_audit=bool(a.birth_source))
                verify(dest,gold,image)
                if policy.record is None:
                    raise ValueError(f'missing prospective decision {decision} in {case}')
                records.append(policy.record)
                _,lane,run,_,_=policy.record
                with np.load(dest/'neural-output.npz') as z:
                    raw=z['raw']
                    prefix_hash=hashlib.sha256(raw[:run-1].tobytes()+raw[run-1,:2].tobytes()).hexdigest()
                    issued=int((raw[:,:,11]>0).sum())
                with np.load(dest/'compound-output.npz') as z:
                    banks=[k for k in z if k in ('claims','tails') or k.startswith('hop_')]
                    won=[int(z[k][run-1,lane,7]) for k in banks]
                roles=read(dest/'run.json')['execution_roles']
                arms.append(dict(issued=issued,residual=roles['rhs_inputs_from_exact_search'],
                                 won=won,prior_sha=prefix_hash))
                if a.birth_source:
                    measured=measure(dest,a.birth_source/case,source_counts[case])
                    assert measured['issued']==issued
                    arms[-1]['visible']=measured['visible']
        roots,lane,run,action,alternative=records[0]
        assert records[0][1:]==records[1][1:] and np.array_equal(roots,records[1][0])
        assert arms[0]['prior_sha']==arms[1]['prior_sha']
        # Charge an active independent token and an exact residual binding one unit each.
        saved={k:arms[1][k]-arms[0][k] for k in ('issued','residual')}
        delta=sum(saved.values())
        if a.birth_source:
            delta=arms[0]['visible']-arms[1]['visible']+rho*saved['issued']
        decisions.append((roots[0],lane,run,action,alternative,delta))
        # Exact two-arm advantage at the sampled decision. Reuse the measured
        # contexts between online episodes; subsequent episodes use the updated actor.
        batch_roots,lanes,runs,long_actions,short_actions,returns=zip(*decisions)
        pairs=torch.tensor(list(zip(long_actions,short_actions)))
        for _ in range(a.replay_steps):
            logits,_,_=actor.propose_children(torch.tensor(np.stack(batch_roots)),
                torch.zeros(len(decisions),2,4),False,torch.tensor(runs))
            conditional=logits[torch.arange(len(decisions)),torch.tensor(lanes)].gather(1,pairs)
            probability=conditional.softmax(-1)[:,0]
            loss=-(probability*torch.tensor(returns)).mean()
            optimizer.zero_grad();loss.backward();optimizer.step()
        rows.append(dict(case=case,root_selection='ordinary' if natural else 'exploratory',run=run,lane=lane,unit=joins[(action-1)%len(joins)][0],
                         alternative='null' if skip else 'prefix',arms=arms,saved=saved,return_difference=delta))
        (a.out/'returns.json').write_text(json.dumps(rows,indent=2)+'\n')
    np.savez_compressed(a.out/'issuer-contexts.npz',roots=np.stack([v[0] for v in decisions]),
                        actions=np.asarray([v[1:5] for v in decisions],dtype=np.int32),
                        advantages=np.asarray([v[5] for v in decisions]))
    build_cache.cleanup()
    model.update(named_boundary=True,return_updates=len(rows),return_lr=a.learning_rate,return_replay=a.replay_steps)
    if a.birth_source:
        model.update(return_objective="visible_constructor_delta_minus_rho_times_issued_delta",training_rho=rho)
    model['child']=torch.cat([v.detach().flatten() for v in (actor.score,actor.row_score,actor.embedding,
                                                            actor.null,actor.row_latent)]).tolist()
    torch.save(actor.state_dict(),a.out/'actor.pt')
    (a.out/'policy.json').write_text(json.dumps(model,separators=(',',':'))+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('exp','checkpoint','out'):p.add_argument(name,type=Path)
    p.add_argument('--updates',type=int,default=56)
    p.add_argument('--learning-rate',type=float,default=.02)
    p.add_argument('--replay-steps',type=int,default=8)
    p.add_argument('--birth-source',type=Path)
    main(p.parse_args())
