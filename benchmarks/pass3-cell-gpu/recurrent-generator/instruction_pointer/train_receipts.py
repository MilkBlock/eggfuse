"""Train continuation credit on native-confirmed request histories from training programs only."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import subprocess
from tempfile import TemporaryDirectory

import torch
from torch.nn.utils.rnn import pad_sequence

from catalog import Catalog
from history import History
from receipt_actor import ReceiptActor
from rule_read import load_actor


def read(path):
    return json.loads(path.read_bytes())


@torch.no_grad()
def capture(folder, receiver, model, selected, seed):
    cat = Catalog(read(folder/'program.json'))
    nodes = model.template_graph(cat)
    history = History(cat,seed)
    teacher = read(folder/'tape.json')
    reference = defaultdict(list)
    for packet in teacher['requests']:
        reference[packet['run']].append(packet)
    probes, pending = [], []
    with (folder/'memory.jsonl').open() as lines:
        for line in lines:
            item = json.loads(line)
            frame = history.snapshot(item,item['run'] in selected)
            if frame is None:
                continue
            mem = model.memory(cat,frame,nodes)
            lookup = {p.address:i for i,p in enumerate(mem.ports)}
            inputs,lanes,base = model.setup(cat,frame,mem)
            keys = model.sequence_key(inputs).tanh()
            pos = {rid:i+1 for i,rid in enumerate(mem.rules)}
            candidates = []
            for p in reference[frame.run]:
                refs = tuple(history.rename((a['address']['token'],a['address']['op'])) for a in p['parents'])
                candidates.append((p['token'],pos[p['rule']],model.request_key(cat,mem,p['rule'],refs,lookup)))
            learned = []
            for _,rid,refs in model.decisions(cat,frame,mem,2):
                if rid is None or refs is None:
                    continue
                parents=[]
                for alias,pc in refs:
                    t=history.inverse[alias]
                    parents.append(dict(address=dict(token=t,op=pc),version=history.visible[t,pc]['version']))
                tag=len(probes)+1
                probes.append(dict(token=tag,run=frame.run,rule=rid,parents=parents))
                learned.append((tag,pos[rid],model.request_key(cat,mem,rid,refs,lookup)))
            pending.append((keys,lanes,base,candidates,learned))
    with TemporaryDirectory() as temp:
        probes_file = Path(temp)/'probes.json'
        probes_file.write_text(json.dumps({**teacher,'requests':probes}))
        audit=json.loads(subprocess.check_output([receiver,'replay',folder/'program.json',folder/'tape.json',
                                                 'audit','--recall',probes_file]))
    if (audit['unused_recall'] or audit['unused'] or audit['counts']['accepted']!=len(teacher['requests'])
            or len(audit['recall_verdicts'])!=len(probes) or audit['counts']['rejected'] or audit['counts']['duplicates']):
        raise ValueError('incomplete supervision')
    wins={key:(w,outcome) for _,key,w,outcome in audit['recall_verdicts']}
    return pending,wins


@torch.no_grad()
def branches(frames, wins, model, rng):
    examples=[]
    ledger=Counter()
    for keys,lanes,base,teacher,learned in frames:
        # Each packet has an actual checked teacher identity, or a receiver rejection.
        # A valid off-reference binding lacks an identity for dedup and is excluded.
        actual=[(wins[tag][0],r,key,wins[tag][1]) for tag,r,key in learned if wins[tag][1]!='off_reference']
        positive=[(w,r,key,'match') for w,r,key in teacher]
        identities={w:r for w,r,_ in teacher}
        random_order=list(positive)
        rng.shuffle(random_order)
        paths=[actual,random_order]
        if positive:
            # Exercise repeats with unfinished siblings and repeats after completion.
            paths.append([p for t in random_order for p in (t,t,t,t)])
            disruptive=actual or [rng.choice(positive)]
            paths.append([p for t in random_order for p in (t,rng.choice(disruptive))])
        for path in paths:
            if not path:
                continue
            # Only full nonterminal waves can influence another decision.
            path = path + [path[-1]] * (-len(path)%len(lanes))
            seen=set()
            past=keys.new_zeros(1,model.width)
            for start in range(0,len(path),len(lanes)):
                wave=path[start:start+len(lanes)]
                verdicts=[]
                for w,_,_,outcome in wave:
                    verdicts.append(outcome if w is None else 'duplicate' if w in seen else 'accepted')
                    if w is not None: seen.add(w)
                _,h=model.sequence_history(torch.stack([x[2] for x in wave])[None],past[None])
                past=h[0]
                remaining=sorted({r for w,r in identities.items() if w not in seen})
                allow=base.new_zeros(base.shape[1],dtype=torch.bool)
                allow[remaining or [0]]=True
                counts=model.counts(verdicts)
                examples.append((past[0],keys,lanes[0],base[0],counts,allow))
                ledger['open' if remaining else 'complete']+=1
                if counts[1]: ledger['duplicate_open' if remaining else 'duplicate_complete']+=1
                if counts[2]: ledger['rejection_open' if remaining else 'rejection_complete']+=1
    return examples, ledger


def train(root, receiver, initial, out, seed=1703):
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    rng=random.Random(seed)
    old=load_actor(initial,True)
    model=ReceiptActor()
    diff=model.load_state_dict(old.state_dict(),strict=False)
    new={n for n,_ in model.named_parameters() if n.startswith('receipt_')}
    if set(diff.missing_keys)!=new or diff.unexpected_keys:
        raise ValueError('unexpected sequence checkpoint')
    for n,p in model.named_parameters(): p.requires_grad_(n in new)
    records=[r for r in read(root/'manifest.json') if r['split']=='train']
    records=[r for r in records if r['origin']=='eggcc'] + rng.sample([r for r in records if r['origin']=='random'],48)
    examples=[]
    ledger=Counter()
    for r in records:
        busy=set(r['busy_runs'])
        idle=set(range(1,r['runs']+1))-busy
        selected=set(rng.sample(sorted(busy),min(96,len(busy)))+rng.sample(sorted(idle),min(48,len(idle))))
        frames,wins=capture(root/r['directory'],receiver,model,selected,seed+r['seed'])
        x,counts=branches(frames,wins,model,rng)
        examples.extend(x)
        ledger.update(counts)
        ledger.update(programs=1,source_runs=len(frames),native_checked_probes=len(wins))
    print('exposure',dict(ledger),flush=True)
    model.to('mps')
    opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=.002)
    groups=[[i for i,e in enumerate(examples) if bool(e[-1][0])==stop] for stop in (False,True)]
    if not all(groups):
        raise ValueError('missing open or exhausted branch')
    for step in range(512):
        batch=[examples[rng.choice(g)] for g in groups for _ in range(16)]
        past,keys,lane,base,counts,allowed=zip(*batch)
        def stack(xs): return torch.stack(xs).to('mps')
        def pad(xs,v=0): return pad_sequence(xs,batch_first=True,padding_value=v).to('mps')
        adjusted=model.correct(stack(past),torch.tensor(counts,device='mps',dtype=torch.float32))
        logits=model.logits(pad(keys),adjusted[:,None],stack(lane)[:,None],pad(base,-torch.inf)[:,None]).squeeze(1)
        loss=-logits.log_softmax(1).masked_fill(~pad(allowed),-torch.inf).logsumexp(1).mean()
        if not torch.isfinite(loss): raise ValueError('nonfinite receipt objective')
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),2.)
        opt.step()
    out.mkdir(exist_ok=True,parents=True)
    state=model.cpu().state_dict()
    if any(not torch.equal(state[k],v) for k,v in old.state_dict().items()):
        raise ValueError('sequence backbone changed')
    torch.save(dict(format='wave-receipt-v1',parameters=state),out/'model.pt')
    (out/'training.json').write_text(json.dumps(dict(device='mps',steps=512,seed=seed,exposure=ledger,
        initial_sha256=hashlib.sha256(initial.read_bytes()).hexdigest()),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','receiver','initial','out'):
        p.add_argument(name,type=Path)
    args=p.parse_args()
    train(args.root,args.receiver,args.initial,args.out)
