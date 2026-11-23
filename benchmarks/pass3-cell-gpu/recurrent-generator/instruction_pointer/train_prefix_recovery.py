"""Supervise low-scoring root reads with native winners and observed teacher prefixes."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import random

import torch
from torch.nn import functional as F

from alternate_proofs import digest
from anchor_set import Domains
from anchor_set_audit import check,load_actor
from higher_cell import read
from history import History
from prefix_policy import Policy,generate
from prefix_recovery import RecoveryHead,features
from ripsat_layout import signatures
from side_boundary import address


@torch.no_grad()
def collect(root,name,weights,binary,out,*,commit_sets=False):
    training={r['directory']:r['seed'] for r in read(root/'manifest.json') if
              r['origin']=='eggcc' and r['split']=='train'}
    if name not in training:
        raise ValueError('expected a training program')
    folder=root/name
    rng=random.Random(1703+training[name])
    model=load_actor(weights,True)
    program=read(folder/'program.json')
    held={i for i,s in enumerate(signatures(program)) if int(s[:8],16)%8==0}
    cat=model.catalog_type(program)
    nodes=model.template_graph(cat)
    tape=read(folder/'tape.json')
    commits=defaultdict(list)
    for req in tape['requests']:
        commits[req['run']].append(req)
    hist=History(cat,1703+training[name])
    contexts=[];keys=[];evidence=[];labels=[];validation=[]
    requests=[]
    positions=[]
    baseline=[]
    stats=Counter()
    with (folder/'memory.jsonl').open() as frames:
        for line in frames:
            frame=json.loads(line)
            # Limit sampling overhead on idle runs, while retaining negative contexts.
            take=bool(commits[frame['run']]) or frame['run']%12==0
            snap=hist.snapshot(frame,take)
            if snap is None:continue
            mem=model.memory(cat,snap,nodes)
            dom=Domains(mem)
            index={p.address:j for j,p in enumerate(mem.ports)}
            if commit_sets:
                for rid,refs in generate(model,cat,mem,Policy(32),selected_rules=set(snap.rules)-held):
                    parents=[dict(address=dict(token=hist.inverse[a],op=pc),
                                  version=mem.ports[index[a,pc]].version) for a,pc in refs]
                    baseline.append(dict(token=len(baseline)+1,run=snap.run,rule=rid,parents=parents))
            truth=defaultdict(set)
            for req in commits[snap.run]:
                rid=req['rule']
                if rid in held or not req['parents']:continue
                js=[index[hist.rename(address(p))] for p in req['parents']]
                anchor=next(i for i,j in enumerate(js) if not cat.seminaive[rid] or mem.ports[j].version>=mem.rules[rid])
                order=(anchor,*(i for i in range(len(js)) if i!=anchor))
                path=tuple(js[i] for i in order)
                truth[rid,order].add(path)
            groups=list(truth)
            absent=[]
            for rid in snap.rules:
                if rid in held:continue
                n=len(cat.atoms[rid])
                for a in range(n if cat.seminaive[rid] else min(n,1)):
                    order=(a,*(i for i in range(n) if i!=a))
                    if (rid,order) not in truth and len(dom.role(cat,mem,rid,a,a)):
                        absent.append((rid,order))
            groups+=rng.sample(absent,min(len(absent),max(2,len(groups))))
            reserved=int.from_bytes(hashlib.sha256(f'{name}/{snap.run}'.encode()).digest()[:4],'big')%5==0
            for rid,order in groups:
                paths=truth.get((rid,order),set())
                sampled=[()]
                for depth,role in enumerate(order):
                    ids=dom.role(cat,mem,rid,order[0],role)
                    if not len(ids):break
                    positive=defaultdict(set)
                    for path in paths:positive[path[:depth]].add(path[depth])
                    prefixes=rng.sample(sorted(positive),min(8,len(positive)))
                    prefixes+=list(dict.fromkeys(p for p in sampled if p not in positive))
                    sampled=[]
                    if not prefixes:break
                    prefixes=torch.tensor(prefixes,dtype=torch.long).reshape(len(prefixes),depth)
                    scores=(model.pair_scores(cat,mem,rid,order[:depth],prefixes,role,ids) if depth else
                            model.root_scores(cat,mem,rid,role,ids,dom)[None])
                    margin=scores-model.thresholds[2 if depth else 1]
                    ctx,ports,ev=features(cat,mem,rid,order,depth,prefixes,ids,margin)
                    js=ids.tolist()
                    local={v:i for i,v in enumerate(js)}
                    for i,prev in enumerate(prefixes.tolist()):
                        prev=tuple(prev)
                        gold={local[j] for j in positive.get(prev,())}
                        missed=(margin[i]<0).nonzero().flatten().tolist()
                        bad=[j for j in missed if j not in gold]
                        hard=sorted(bad,key=lambda j:-float(margin[i,j]))[:4]
                        chosen=sorted(set(hard+rng.sample(bad,min(len(bad),8)))|{j for j in gold if margin[i,j]<0})
                        if depth+1<len(order) and len(sampled)<2:
                            other=[k for k in range(len(js)) if k not in gold]
                            if other:
                                k=max(other,key=lambda k:float(margin[i,k]))
                                sampled.append((*prev,js[k]))
                        if not chosen:continue
                        contexts.append(ctx[i].expand(len(chosen),-1))
                        keys.append(ports[chosen])
                        evidence.append(ev[i,chosen])
                        for k in chosen:
                            pos=len(labels)
                            labels.append(k in gold)
                            validation.append(reserved)
                            if depth+1!=len(order):continue
                            pp=[None]*len(order)
                            for r,j in zip(order,(*prev,js[k]),strict=True):
                                port=mem.ports[j];alias,pc=port.address
                                pp[r]=dict(address=dict(token=hist.inverse[alias],op=pc),version=port.version)
                            positions.append(pos)
                            requests.append(dict(token=len(requests)+1,run=snap.run,rule=rid,parents=pp))
    verdicts=check(folder,binary,tape,requests)['recall_verdicts']
    winners=torch.full((len(labels),),-1,dtype=torch.long) if commit_sets else None
    if {row[1] for row in verdicts}!=set(range(1,len(requests)+1)):
        raise ValueError('incomplete native label set')
    for run,token,winner,reason in verdicts:
        pos=positions[token-1]
        req=requests[token-1]
        if req['run']!=run:raise ValueError('misaligned native labels')
        if labels[pos] and winner is None:raise ValueError('native rejected the teacher proof')
        stats['alternative_native_positive']+=int(not labels[pos] and winner is not None)
        labels[pos]=winner is not None
        if commit_sets:
            winners[pos]=winner or 0
    out.mkdir(parents=True,exist_ok=True)
    tensors=dict(ctx=torch.cat(contexts),ports=torch.cat(keys),ev=torch.cat(evidence),
                 y=torch.tensor(labels),reserved=torch.tensor(validation))
    if commit_sets:
        base_verdicts=check(folder,binary,tape,baseline)['recall_verdicts']
        covered=set()
        for run,t,w,_ in base_verdicts:
            if baseline[t-1]['run']!=run:
                raise ValueError('baseline proposal label is from another Run')
            if w is not None:
                covered.add(w)
        tensors.update(winner=winners,covered=torch.tensor(sorted(covered),dtype=torch.long))
        stats.update(baseline_proposals=len(baseline),baseline_distinct=len(covered))
    torch.save(tensors,out/(name+'.pt'))
    report=dict(data=digest(out/(name+'.pt')),program=digest(folder/'program.json'),
                tape=digest(folder/'tape.json'),base=digest(weights),receiver=digest(binary),
                holdout_rule_count=len(held),examples=len(labels),positive=sum(labels),
                native_checked=len(requests),**stats)
    (out/(name+'.json')).write_text(json.dumps(report,indent=2)+'\n')


def fit(root,data,weights,out):
    names=sorted(r['directory'] for r in read(root/'manifest.json') if r['origin']=='eggcc' and r['split']=='train')
    reports={name:read(data/(name+'.json')) for name in names}
    parts=[]
    for name,report in reports.items():
        file=data/(name+'.pt')
        if (digest(file)!=report['data'] or report['base']!=digest(weights) or
            digest(root/name/'tape.json')!=report['tape']):
            raise ValueError('incompatible recovery examples')
        parts.append(torch.load(file,map_location='cpu',weights_only=True))
    ctx,ports,ev,y,valid=[torch.cat([d[k] for d in parts]) for k in ('ctx','ports','ev','y','reserved')]
    pos=(y&~valid).nonzero().flatten();neg=(~y&~valid).nonzero().flatten()
    if not len(pos) or not len(neg) or not valid.any():raise ValueError('empty recovery split')
    width=ports.shape[1]
    torch.manual_seed(1703)
    head=RecoveryHead(width).to('mps')
    opt=torch.optim.AdamW(head.parameters(),lr=.003)
    x,k,e,ys=[t.to('mps') for t in (ctx,ports,ev,y.float())]
    for epoch in range(32):
        positive=pos[torch.randperm(len(pos))]
        for batch in positive.split(96):
            other=neg[torch.randint(len(neg),(len(batch)*2,))]
            ix=torch.cat((batch,other)).to('mps')
            logits=head(x[ix],k[ix],e[ix])
            loss=F.binary_cross_entropy_with_logits(logits,ys[ix])
            opt.zero_grad();loss.backward()
            torch.nn.utils.clip_grad_norm_(head.parameters(),2.);opt.step()
    head.cpu().eval()
    with torch.no_grad():
        scores=head(ctx[valid],ports[valid],ev[valid])
    targets=y[valid]
    thresholds=[]
    for cut in [i/4 for i in range(-16,21)]:
        chosen=scores>=cut
        tp=int((targets&chosen).sum())
        # F1 on reserved examples; validation retains the sampled hard-negative distribution.
        f1=2*tp/max(int(targets.sum()+chosen.sum()),1)
        thresholds.append((f1,cut,tp,int(chosen.sum())))
    f1,cut,hits,issued=max(thresholds)
    margin=ev[valid,0]*8
    margin_trials=[]
    for threshold in [-.125,-.25,-.5,-1.,-2.,-4.,-8.,-16.,-32.]:
        chosen=margin>=threshold
        tp=int((targets&chosen).sum())
        margin_trials.append((2*tp/max(int(targets.sum()+chosen.sum()),1),threshold))
    margin_f1,margin_cut=max(margin_trials)
    out.mkdir(parents=True,exist_ok=True)
    torch.save(head.state_dict(),out/'head.pt')
    (out/'training.json').write_text(json.dumps(dict(width=width,base=digest(weights),budget=4,
        cut=cut,margin_cut=margin_cut,margin_f1=margin_f1,head=digest(out/'head.pt'),training=reports,valid_examples=int(valid.sum()),
        valid_positives=int(targets.sum()),valid_selected=issued,valid_hits=hits,valid_f1=f1,
        training_positive=len(pos),training_negative=len(neg),device='mps',epochs=32),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','weights','binary','data','out'):p.add_argument(key,type=Path)
    p.add_argument('--collect',nargs='+')
    p.add_argument('--commit-sets',action='store_true',help='record native proof equivalence and base-policy coverage for training')
    a=p.parse_args()
    torch.set_num_threads(1)
    if a.collect:
        for name in a.collect:collect(a.root,name,a.weights,a.binary,a.data,commit_sets=a.commit_sets)
    else:
        fit(a.root,a.data,a.weights,a.out)
