"""Fit the parent pointer on unfinished sibling commitments from native training snapshots."""
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

from history import stream
from parent_actor import ParentActor
from rule_read import load_actor


def read(path):
    return json.loads(path.read_bytes())


def native_probes(folder, binary, selected, seed, old, rng):
    """Collect model requests and perturbed teacher requests, and get their actual verdicts."""
    tape = read(folder/'tape.json')
    teacher = defaultdict(list)
    for packet in tape['requests']:
        teacher[packet['run']].append(packet)
    proposals, sources = [], {}
    nodes = None
    for cat, snap in stream(folder,seed,selected):
        if nodes is None:
            nodes = old.template_graph(cat)
        # stream exposes renamed addresses. Zip each label with the exact teacher
        # request to translate it back for the native checker. Model-only addresses
        # that do not occur in teacher parents require the full port name map.
        mem = old.memory(cat,snap,nodes)
        actions = [(rid,refs) for _,rid,refs in old.decisions(cat,snap,mem,1)
                   if rid is not None and refs]
        for rid,refs in rng.sample(snap.targets,min(6,len(snap.targets))):
            if refs and mem.ports:
                j = rng.randrange(len(refs))
                table = cat.atoms[rid][j][0]
                same_type = [p for p in mem.ports if p.table == table]
                changed = (*refs[:j],rng.choice(same_type).address,*refs[j+1:])
                actions.append((rid,changed))
        sources[snap.run] = actions
    # Materialize exactly the same selected snapshots and reversible random names.
    from history import History
    from catalog import Catalog
    history = History(Catalog(read(folder/'program.json')),seed)
    tagged = defaultdict(list)
    with (folder/'memory.jsonl').open() as f:
        for line in f:
            raw=json.loads(line)
            frame=history.snapshot(raw,raw['run'] in selected)
            if frame is None:
                continue
            for rid,refs in sources[frame.run]:
                parents=[]
                for alias,pc in refs:
                    a=(history.inverse[alias],pc)
                    parents.append(dict(address=dict(token=a[0],op=pc),version=history.visible[a]['version']))
                tag=len(proposals)+1
                proposals.append(dict(token=tag,run=frame.run,rule=rid,parents=parents))
                tagged[frame.run].append((tag,rid,refs))
    with TemporaryDirectory() as temp:
        file=Path(temp)/'probes.json'
        file.write_text(json.dumps({**tape,'requests':proposals}))
        checked=json.loads(subprocess.check_output([binary,'replay',folder/'program.json',folder/'tape.json',
                                                    'audit','--recall',file]))
    if (checked['unused'] or checked['unused_recall'] or checked['counts']['accepted']!=len(tape['requests'])
            or len(checked['recall_verdicts'])!=len(proposals)):
        raise ValueError('incomplete teacher prefix replay')
    verdicts={k:(w,v) for _,k,w,v in checked['recall_verdicts']}
    return teacher,tagged,verdicts


def log_mass(values, groups, size):
    result=values.new_full((size,),-torch.inf)
    if len(values):
        maxima=result.scatter_reduce(0,groups,values,reduce='amax')
        mass=values.new_zeros(size).scatter_add_(0,groups,(values-maxima[groups]).exp())
        result=mass.log()+maxima
    return result


def capture_read(history, rid, roles, selected, scores, desired, samples):
    # All equal feature vectors get exactly the same learned logit correction.
    # Grouping the loss terms keeps the CPU dataset small without truncating the domain.
    feat=history.features(rid,roles,selected,scores)
    ok=scores.isfinite()
    chosen=torch.zeros_like(ok)
    for row,role in enumerate(roles):
        chosen[row,desired[role]]=True
    features,idx=torch.unique(feat[ok],dim=0,return_inverse=True)
    if len(features)>1 and (chosen & ok).any():
        values=scores[ok]
        target=chosen[ok]
        samples.append((features,log_mass(values,idx,len(features)),
                         log_mass(values[target],idx[target],len(features))))
    return scores


@torch.no_grad()
def collect(root,binary,model,seed,rng):
    records=[r for r in read(root/'manifest.json') if r['split']=='train']
    records=[r for r in records if r['origin']=='eggcc']+rng.sample([r for r in records if r['origin']=='random'],48)
    samples=[]
    ledger=Counter()
    for r in records:
        folder=root/r['directory']
        busy=r['busy_runs']
        selected=set(rng.sample(busy,min(len(busy),96)))
        if not selected:
            continue
        rename_seed=seed+r['seed']
        teacher,tagged,verdicts=native_probes(folder,binary,selected,rename_seed,model,rng)
        nodes=None
        for cat,snap in stream(folder,rename_seed,selected):
            if nodes is None:
                nodes=model.template_graph(cat)
            mem=model.memory(cat,snap,nodes)
            lookup={p.address:i for i,p in enumerate(mem.ports)}
            _,lanes,_=model.setup(cat,snap,mem)
            groups=defaultdict(list)
            for (rid,refs),packet in zip(snap.targets,teacher[snap.run],strict=True):
                if refs:
                    groups[rid].append((packet['token'],refs))
            for rid,items in groups.items():
                history=model.parent_history(lookup)
                accepted=set()
                for tag,rule,refs in tagged[snap.run]:
                    if rule!=rid:
                        continue
                    w,outcome=verdicts[tag]
                    if outcome=='off_reference':
                        continue
                    verdict='duplicate' if w in accepted else 'accepted' if w is not None else outcome
                    history.issue(rid,refs)
                    history.resolve([(rid,refs)],[verdict])
                    if w is not None:
                        accepted.add(w)
                    ledger['probe_'+verdict]+=1
                remaining=[(w,refs) for w,refs in items if w not in accepted]
                rng.shuffle(remaining)
                pending=[]
                for i,(w,refs) in enumerate(remaining[:24]):
                    desired=tuple(lookup[a] for a in refs)
                    def observe(rule,roles,selected,scores):
                        return capture_read(history,rule,roles,selected,scores,desired,samples)
                    model.references(cat,mem,lanes[i%len(lanes)],rid,refs,observe)
                    history.issue(rid,refs)
                    pending.append(((rid,refs),'accepted'))
                    if rng.random()<0.3:
                        history.issue(rid,refs)
                        pending.append(((rid,refs),'duplicate'))
                    if len(pending)>=len(lanes) or rng.random()<0.3:
                        actions,outcomes=zip(*pending)
                        history.resolve(actions,outcomes)
                        pending.clear()
                ledger['remaining_sampled']+=min(len(remaining),24)
            ledger['source_runs']+=1
        ledger['programs']+=1
    return samples,ledger


def train(root,binary,initial,out,seed):
    rng=random.Random(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    old=load_actor(initial,True)
    model=ParentActor()
    missing=model.load_state_dict(old.state_dict(),strict=False)
    if missing.missing_keys!=['parent_read.weight'] or missing.unexpected_keys:
        raise ValueError('expected native-receipt checkpoint')
    for name,p in model.named_parameters():
        p.requires_grad_(name=='parent_read.weight')
    samples,ledger=collect(root,binary,model,seed,rng)
    if not samples:
        raise ValueError('no history-sensitive choices')
    print('exposure',len(samples),dict(ledger),flush=True)
    head=model.parent_read.to('mps')
    opt=torch.optim.AdamW(head.parameters(),lr=.035)
    for step in range(512):
        feats,all_mass,gold_mass=zip(*rng.choices(samples,k=64))
        x=pad_sequence(feats,batch_first=True).to('mps')
        def pad(v): return pad_sequence(v,batch_first=True,padding_value=-torch.inf).to('mps')
        delta=head(x).squeeze(-1)
        loss=((pad(all_mass)+delta).logsumexp(1)-(pad(gold_mass)+delta).logsumexp(1)).mean()
        if not loss.isfinite(): raise ValueError('invalid pointer loss')
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
    state=model.cpu().state_dict()
    if any(not torch.equal(state[k],v) for k,v in old.state_dict().items()):
        raise ValueError('backbone changed')
    out.mkdir(parents=True,exist_ok=True)
    torch.save(dict(format='parent-history-v1',parameters=state),out/'model.pt')
    (out/'training.json').write_text(json.dumps(dict(seed=seed,device='mps',steps=512,reads=len(samples),
        exposure=ledger,weights=head.weight.tolist(),initial_sha256=hashlib.sha256(initial.read_bytes()).hexdigest()),
        indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('root','binary','initial','out'):
        parser.add_argument(name,type=Path)
    parser.add_argument('--seed',type=int,default=1703)
    args=parser.parse_args()
    train(args.root,args.binary,args.initial,args.out,args.seed)
