"""Interactive native rollouts, followed by isolated exact comparisons and paired issuance credit."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import subprocess

import torch
from policy import ROLES, TABLES, WIDTH, fields, train
from tempfile import TemporaryDirectory


def compile_case(compiler,root,seed,kind):
    rng=random.Random(seed)
    keys=rng.sample(range(8),8)
    ls=keys[:3]
    rs=keys[3:6]+([ls[seed%3]] if kind!='absent' else [])
    initial=[f'(L {k})' for k in ls]+[f'(R {k})' for k in rs]
    if seed%3!=1:
        initial.append('(Tag 0)')
    if kind=='reuse':
        k=ls[seed%3]
        initial.append(f'(C (Both (L {k}) (R {k})))')
    rng.shuffle(initial)
    source=Path(__file__).with_name('family.egg').read_text()
    folder=root/f'{kind}-{seed}'
    path=folder.with_suffix('.egg')
    path.write_text(source[:source.index('(L 1)')]+'\n'.join(initial)+'\n'+source[source.index('(run-schedule'):])
    subprocess.run([compiler,'compile','--source',path,'--output',folder],check=True,capture_output=True)
    return folder/'program.json'


class Memory:
    def __init__(self,policy):
        self.policy=policy
        self.rows={}
        self.keys={}
        self.choices={}
        self.stats=Counter()

    def install(self,items):
        for owner,slot,version,table,values in items:
            if table not in ('L','R','Tag','Both','C','D','Use'):
                raise ValueError(table)
            k=values[0]['Int'] if table in ('L','R','Tag') else None
            self.rows[owner,slot]=(version,fields(table,k,self.choices.get(owner,False),slot))

            self.encode((owner,slot))

    def encode(self,key):
        self.keys[key]=self.policy.keys(torch.tensor(self.rows[key][1]))
        self.stats["encodings"]+=1

    def read(self,role,selected=None,used=()):
        ids=sorted(self.rows)
        if not ids:
            return None
        keys=torch.stack([self.keys[i] for i in ids])
        q=torch.tensor(self.rows[selected][1] if selected else [0.]*WIDTH)
        query=self.policy.roles.weight[ROLES.index(role)]+self.policy.condition(q)
        scores=self.policy.score_keys(keys[None],query[None])[0]
        self.stats['scores']+=len(ids)
        self.stats['reads']+=1
        # Mask only addresses the policy itself has already tried in this Run.
        for i,key in enumerate(ids):
            if key in used:
                scores[i+1]=-torch.inf
        j=scores.argmax().item()
        return ids[j-1] if j else None


@torch.no_grad()
def rollout(binary,program,policy,mode,force_skip=None):
    with subprocess.Popen([binary,program],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True) as proc:
        def read():
            line=proc.stdout.readline()
            if not line:
                raise RuntimeError(f'native receiver ended early: {proc.wait()}')
            return json.loads(line)
        hello=read()
        rules={name:rid for rid,name in hello['rules']}
        mem=Memory(policy)
        mem.install(hello['initial'])
        serial=max((i for i,_ in mem.rows),default=0)
        packets=0
        selected=None
        stage_reads=[]
        skip_feature=None
        uses=[]
        retired_c=None
        transfers=0
        root_key=None
        def issue(rule,parents,compound=False):
            nonlocal serial,packets
            serial+=1
            packets+=1
            mem.choices[serial]=compound
            return dict(owner=serial,rule=rules[rule],parents=[[i,s,mem.rows[i,s][0]] for i,s in parents],compound=compound)
        for stage in range(3):
            batch=[]
            if stage==0:
                tried=set()
                while len(tried)<len(mem.rows):
                    left=mem.read('left',used=tried)
                    if left is None:
                        break
                    tried.add(left)
                    right=mem.read('right',None if mode=='unconditioned' else left)
                    if right is None:
                        continue
                    root_key=mem.rows[left][1]
                    full=mode in ('full','old-owner') or (mode in ('learned','unconditioned') and policy.macro_logit(torch.tensor(root_key)).item()>=0)
                    if mode=='bad-owner':
                        pkt=issue('Both',[left,right])
                        pkt['parents'][1][0]=serial+1000
                    elif mode=='stale':
                        pkt=issue('Both',[left,right])
                        pkt['parents'][1][2]+=1
                    else:
                        pkt=issue('Both',[left,right],full)
                    batch.append(pkt)
                    break
            if stage==1:
                both=mem.read('advance')
                if both:
                    # At this decision the model knows only the accepted token
                    # it chose earlier and the selected export's observed state.
                    skip_feature=float(mem.choices.get(both[0],False))
                    skip=(policy.skip(torch.tensor([skip_feature])).item()>0
                          if force_skip is None else force_skip)
                    if not skip:
                        batch.append(issue('C',[both]))
                tag=mem.read('independent')
                if tag:
                    batch.append(issue('D',[tag]))
            if stage==2:
                selected=mem.read('use')
                if selected:
                    if mode=='old-owner' and retired_c is not None:
                        selected=retired_c
                    uses.append([selected[1],mem.choices.get(selected[0],False)])
                    batch.append(issue('Use',[selected]))
            proc.stdin.write(json.dumps(batch)+'\n')
            proc.stdin.flush()
            boundary=read()
            for key in map(tuple,boundary['retired']):
                version,features=mem.rows[key]
                features[-1]=1.
                mem.encode(key)
                transfers+=1
                if features[TABLES.index('C')]:
                    retired_c=key
            mem.install(boundary['exports'])
            stage_reads.append(boundary['reads'])
        result=read()
        proc.stdin.close()
        if proc.wait():
            raise RuntimeError('native receiver failed')
    return dict(source=result,paid=packets,receiver_reads=stage_reads[-1],rejected=boundary['rejected'],
                pointer_scores=mem.stats['scores'],queries=mem.stats['reads'],uses=uses,
                encodings=mem.stats['encodings'],skip_feature=skip_feature,root_features=root_key,transfers=transfers,internal=result['internal'])


def exact(binary,program,plans):
    data=subprocess.check_output([binary,program,plans],input='{"baseline":true,"audit":true}\n',text=True)
    return json.loads(data)


def compare(out,ref):
    checks={k:out['source'][k]==ref[k] for k in ('state_sha','rhs','writes','resumes','events','schedule')}
    def graph_events(runs):
        return [[e for e in run if e[0]!='resume'] for run in runs]
    checks['graph_events']=graph_events(out['source']['events'])==graph_events(ref['events'])
    return checks


def semantic(checks):
    return all(checks[k] for k in ('state_sha','rhs','writes','schedule','graph_events'))


def main(a):
    torch.set_num_threads(1)
    policy=train(1703)
    opt=torch.optim.Adam(policy.block.parameters(),lr=.15)
    # The zero-logit initialization has no preference; fit only the block decision here.
    torch.nn.init.zeros_(policy.block.weight)
    torch.nn.init.zeros_(policy.block.bias)
    torch.nn.init.zeros_(policy.skip.weight)
    torch.nn.init.zeros_(policy.skip.bias)
    skip_pairs=[]
    report={'train':[],'eval':[]}
    with TemporaryDirectory() as tmp:
        root=Path(tmp);plans=root/'plans.json';plans.write_text('[]')
        for seed in range(24):
            kind=('fresh','reuse','absent')[seed%3] if seed<12 else ('reuse','fresh','absent')[(seed//3+seed)%3]
            program=compile_case(a.compiler,root,seed,kind)
            if seed<12:
                forks={(mode,skip):rollout(a.native,program,policy,mode,force_skip=skip)
                       for mode in ('leaf','full') for skip in (False,True)}
                ref=exact(a.reference,program,plans)
                same=lambda r: semantic(compare(r,ref))
                # Constrained return: require the same source outcomes, then
                # charge paid actions including rejected issues and validation.
                def cost(r):
                    return r['paid']+r['receiver_reads']/8+r['rejected']+100*int(not same(r))
                for mode in ('leaf','full'):
                    send,skip=forks[mode,False],forks[mode,True]
                    if skip['skip_feature']!=send['skip_feature']:
                        raise ValueError('different stage-two decision points')
                    if send['skip_feature'] is not None:
                        skip_pairs.append((send['skip_feature'],cost(send)-cost(skip)))
                if skip_pairs and send['skip_feature'] is not None:
                    # Maximize expected paired return for the binary action;
                    # normalize each action context separately for optimization.
                    xs=torch.tensor([x for x,_ in skip_pairs])[:,None]
                    gains=torch.tensor([v for _,v in skip_pairs])
                    sop=torch.optim.Adam(policy.skip.parameters(),lr=.1)
                    for _ in range(40):
                        prob=policy.skip(xs)[:,0].sigmoid()
                        loss=-torch.stack([(prob[xs[:,0]==b]*gains[xs[:,0]==b]).mean()/
                                      gains[xs[:,0]==b].abs().mean().clamp_min(1)
                                      for b in xs.unique()]).mean()
                        sop.zero_grad();loss.backward();sop.step()
                # Freeze the newly fitted continuation policy in both root forks.
                leaf=rollout(a.native,program,policy,'leaf')
                full=rollout(a.native,program,policy,'full')
                gain=cost(leaf)-cost(full)
                if leaf['root_features']!=full['root_features']:
                    raise ValueError('fork did not share the root decision')
                x=leaf['root_features']
                if x:
                    loss=-policy.macro_logit(torch.tensor(x)).sigmoid()*gain
                    opt.zero_grad();loss.backward();opt.step()
                report['train'].append(dict(seed=seed,kind=kind,gain=gain,decision=x is not None,
                                            leaf_ok=same(leaf),full_ok=same(full)))
            else:
                arms={m:rollout(a.native,program,policy,m) for m in ('leaf','full','learned','bad-owner','stale','old-owner','unconditioned')}
                ref=exact(a.reference,program,plans)
                for r in arms.values():
                    r['checks']=compare(r,ref)
                    del r['source'],r['root_features']
                report['eval'].append(dict(seed=seed,kind=kind,arms=arms))
    report['skip_pairs']=skip_pairs
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    torch.save(policy.state_dict(),a.out/'pointer.pt')
    for mode in ('leaf','full','learned','bad-owner','stale','old-owner','unconditioned'):
        rows=[e['arms'][mode] for e in report['eval']]
        print(mode,sum(semantic(r['checks']) for r in rows),sum(r['paid'] for r in rows),
              sum(r['internal'] for r in rows),sum(r['rejected'] for r in rows),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('compiler','native','reference','out'):
        p.add_argument(arg,type=Path)
    main(p.parse_args())
