"""Paired ablation of recurrent root proposals on the compiled two-parent fixture."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import subprocess
import sys
from tempfile import TemporaryDirectory

import torch

from model import HIDDEN, LEAVES, RANKS, ROWS, set_loss
from port_context import ExportMemory, PortContextActor

ACTIONS = LEAVES * RANKS
CHOICES = (0, RANKS)
FEATURES = 10


def sample(rng, size, balanced=False):
    examples = []
    for i in range(size):
        mask = i % 4 if balanced else rng.randrange(4)
        a, b = rng.randrange(2), 2 + rng.randrange(2)
        # Static candidate 0 is (first L, first R); candidate 1 is (second L, second R).
        # Disjoint scalar domains exclude cross-pair solutions in this ablation.
        rows = [('L', a), ('R', a if mask & 1 else a ^ 1),
                ('L', b), ('R', b if mask & 2 else b ^ 1)]
        rows.extend(('R', k) for k in rng.sample(range(10,64), rng.randrange(5)))
        examples.append((rows,mask))
    return examples


def columns(table, key):
    # Fixed encoding of the observable table and scalar. No joins or membership tests.
    return (5 if table == 'R' else 0) + min(key,4)


def inputs(examples):
    batch = len(examples)
    obs = torch.zeros(batch,ACTIONS,8,dtype=torch.long)
    obs[:,:,0] = -1
    obs[:,CHOICES,0] = torch.tensor([0,1])
    prev = torch.zeros(batch,ROWS,HIDDEN+4)
    target = torch.zeros(batch,ACTIONS)
    features = torch.zeros(batch,8,FEATURES)
    live = torch.zeros(batch,8,dtype=torch.bool)
    for i,(rows,mask) in enumerate(examples):
        for j,(table,key) in enumerate(rows):
            features[i,j,columns(table,key)] = 1
            live[i,j] = True
        for bit,index in enumerate(CHOICES):
            target[i,index] = (mask >> bit) & 1
    return obs,prev,target,features,live


def trial(seed,steps,device):
    rng = random.Random(seed)
    torch.manual_seed(seed)
    actor = PortContextActor(FEATURES).to(device)
    blind = PortContextActor(FEATURES).to(device)
    blind.load_state_dict(actor.state_dict())
    arms = [(name, model, torch.optim.Adam(model.parameters(),lr=.008))
            for name,model in [('context',actor),('blind',blind)]]
    for _ in range(steps):
        obs,prev,target,features,live = (x.to(device) for x in inputs(sample(rng,48)))
        for name,model,opt in arms:
            ports = (*model.encode_ports(features), live) if name=='context' else None
            logits,_ = model.step(obs,prev,ports=ports)
            loss=set_loss(logits,target)
            opt.zero_grad()
            loss.backward()
            opt.step()
    return {name:model.cpu().eval() for name,model,_ in arms}


def updates(rows):
    return {i+1:(0,tuple(float(c==columns(t,k)) for c in range(FEATURES)))
            for i,(t,k) in enumerate(rows)}


@torch.no_grad()
def check(models, examples):
    obs,prev,_,_,_ = inputs(examples[:1])
    counts = {name:Counter() for name in ('blind','context','wrong_context')}
    actions = {name:[] for name in counts}
    for i,(rows,mask) in enumerate(examples):
        memory = ExportMemory(models['context'])
        new = updates(rows)
        memory.publish(new)
        memory.publish(new)
        if memory.encoded != len(rows):
            raise AssertionError('re-encoded an unchanged export')
        ports = memory.snapshot()
        reversed_memory = ExportMemory(models['context'])
        reversed_memory.publish(dict(reversed(list(new.items()))))
        if not all(torch.equal(a,b) for a,b in zip(ports,reversed_memory.snapshot())):
            raise AssertionError('input order changed canonical projections')
        # Next case always has a different target in the balanced test.
        other = ExportMemory(models['context'])
        other.publish(updates(examples[(i+1)%len(examples)][0]))
        for name,model in [('blind',models['blind']),('context',models['context']),
                           ('wrong_context',models['context'])]:
            bank = {'blind':None,'context':ports,'wrong_context':other.snapshot()}[name]
            logits,_ = model.step(obs,prev,ports=bank)
            selected = [CHOICES.index(n-1) for n in logits.argmax(-1)[0].tolist() if n]
            wanted = {bit for bit in range(2) if mask & (1<<bit)}
            actions[name].append(selected)
            counts[name].update(exact=int(set(selected)==wanted), proposals=len(selected),
                                duplicates=len(selected)-len(set(selected)), missed=len(wanted-set(selected)),
                                extra=len(set(selected)-wanted), trials=1,
                                scores=0 if bank is None else ROWS*bank[0].shape[1])
    return counts,actions


def verify(args,examples,actions):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'named-only-verifier'))
    from accept import evaluate
    fixture = (Path(__file__).resolve().parent.parent/'named-only-verifier/two-parents.egg').read_text()
    rules = fixture[:fixture.index('(L 7)')]
    agreement={name:Counter() for name in actions}
    with TemporaryDirectory() as tmp:
        root=Path(tmp)
        plans=root/'plans.json'
        plans.write_text('[]')
        source=root/'input.egg'
        for i,(rows,_) in enumerate(examples):
            source.write_text(rules + ''.join(f'({t} {k})\n' for t,k in rows) + '(run-schedule (run join))\n')
            dest=root/f'case-{i}'
            subprocess.run([args.compiler,'compile','--source',source,'--output',dest],
                           check=True,capture_output=True)
            path=dest/'program.json'
            # Attach the actual ingress handles for the two fixed action tuples.
            # Every initial row in this constructor-only fixture is an op-0 fact.
            addresses={(r['table'],r['values'][0]['value']): j+1
                       for j,r in enumerate(json.loads(path.read_bytes())['initial'])}
            for name in actions:
                issued=[dict(run=1,rule=0,parents=[
                    [dict(Fact=dict(cell=addresses[rows[bit*2+j-1]],op=0)),0] for j in (1,2)]) for bit in actions[name][i]]
                result=evaluate(args.verifier,args.reference,path,plans,issued)
                agreement[name].update(passed=int(result['status']=='pass'),
                                       proposals=len(issued), accepted=result['accepted'],
                                       rejected=result['rejected'], named_reads=result['named_reads'])
    return dict(agreement)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('compiler','verifier','reference','out'):
        p.add_argument(name,type=Path)
    p.add_argument('--steps',type=int,default=500)
    p.add_argument('--device',choices=['cpu','mps'],default='cpu')
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    torch.set_num_threads(1)
    tests=sample(random.Random(81713),256,balanced=True)
    report={}
    for seed in (1703,1709):
        models=trial(seed,args.steps,args.device)
        counts,actions=check(models,tests)
        native=verify(args,tests[:32],actions)
        torch.save(models['context'].state_dict(),args.out/f'context-{seed}.pt')
        report[seed]=dict(metrics=counts,native=native,native_cases=32)
        print(seed,report[seed],flush=True)
    (args.out/'results.json').write_text(json.dumps(dict(training_device=args.device,steps=args.steps,
        evaluation_device='cpu',runs=report),indent=2)+'\n')
