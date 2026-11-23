"""Collect the realized work of model-issued graphs from their sealed native receipts."""
import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory

import torch

from alternate_proofs import digest
from anchor_set_audit import load_actor
from higher_cell import read
from live_ripsat import GraphIssuer,evaluate
from online import RESIDUAL,execute
from prefix_policy import Policy
from train_ripsat import layout_id


def signature(rule,parents):
    return (rule,tuple((p['address']['token'],p['address']['op'],p['version']) for p in parents))


class CreditIssuer(GraphIssuer):
    ownership_feedback=True

    def __init__(self,actor,donor,target,baked,*,omit,explore,seed,policy=None,attach=False):
        super().__init__(actor,donor,target,baked,native=True)
        self.attach=attach
        self.omit=omit
        self.explore=explore
        self.withheld={i for i,g in enumerate(self.layouts) if int(layout_id(g)[:8],16)%8==0}
        self.rng=random.Random(seed)
        self.policy=policy
        self.log={}
        self.menus={}
        self.omissions={}
        self.rewards={}
        self.alternatives=set()
        self.claim_counts=Counter()
        self.run=0
        self.run_choices={}

    def select(self,req,options,history,domains):
        if self.policy is None or self.policy.static_scores is None:
            return super().select(req,options,history,domains)
        if not options:
            return None
        self.counts['root_decisions']+=1
        rid=req['rule']
        # GraphIssuer builds a single eligible menu per rule on this source Run.
        if rid not in self.run_choices:
            self.run_choices[rid]=self.policy.static_choice(options)
            self.claim_counts['static_menu_decisions']+=1
        uid=self.run_choices[rid]
        return self.bind_layout(req,uid,history,domains) if uid is not None else None

    def choose_layout(self,req,options,context):
        if self.policy is not None:
            return self.policy.select(req,options,context,self)
        if self.explore:
            options=[i for i in options if i not in self.withheld]
            if not options:
                return None
        baseline=super().choose_layout(req,options,context)
        if not self.explore:
            return baseline
        # Every eligible graph can be sampled. Equal mass per size prevents a
        # large collection of short graphs from absorbing all exploration.
        sizes=Counter(len(self.layouts[u]) for u in options)
        draw=self.rng.random()
        action=baseline
        if draw<.15:
            action=None
        elif draw<.6:
            size=self.rng.choice(sorted(sizes))
            action=self.rng.choice([u for u in options if len(self.layouts[u])==size])
        probability=.4*(baseline==action)
        probability+=.15 if action is None else .45/(len(sizes)*sizes[len(self.layouts[action])])
        menu=self.menus.setdefault(tuple(options),len(self.menus))
        self.log[req['token']]=[menu,context.tolist(),action,probability,baseline,req['run']]
        return action

    def batch(self,frame,history,snap,roots,next_token):
        self.run_choices.clear()
        feedback=frame['layout_feedback']
        owners={}
        for root,token,rule,parents in feedback['claims']:
            # Several signed steps can name the same premise tuple. The first
            # scheduled request is verified first under the native source order.
            owners.setdefault(signature(rule,parents),(root,token))
        for root,token,reason in feedback['outcomes']:
            if reason=='external_alternative':
                self.alternatives.add(token)
            else:
                self.rewards[token]=(root,reason)
        self.run=snap.run
        children,next_token=super().batch(frame,history,snap,roots,next_token)
        if children:
            raise ValueError('native graphs unexpectedly materialized on the host')
        self.claim_counts['published_steps']+=len(feedback['claims'])
        remaining=[]
        for req in roots:
            owner=owners.get(signature(req['rule'],req['parents'])) if owners else None
            if owner is not None:
                if 'graph' in req:
                    self.claim_counts['matching_roots_with_successors']+=1
                    if self.attach:
                        req['graph']['owner']=owner[1]
                else:
                    self.claim_counts['matching_plain_roots']+=1
                    if self.omit:
                        self.omissions[owner[1]]=self.omissions.get(owner[1],0)+1
                        continue
            remaining.append(req)
        roots[:]=remaining
        return [],next_token

    def credit(self,ept):
        returns={}
        totals=Counter()
        effects={int(t):v for t,v in ept.pop('internal_tokens').items()}
        if [sum(v[k] for v in effects.values()) for k in range(4)]!=ept['signed_internal']:
            raise ValueError('per-token effective operation credits differ from the internal ledger')
        if any(self.rewards.get(t,(None,None))[1]!='accepted' for t in effects):
            raise ValueError('internal effects do not belong to a confirmed receipt')
        for token,(root,reason) in self.rewards.items():
            counts=returns.setdefault(root,Counter())
            counts['attempts']+=1
            if reason=='accepted':
                counts['accepted']+=1
                if token in self.omissions:
                    counts['owned_valid']+=1
                elif token not in self.alternatives:
                    counts['uncontested']+=1
                    counts['uncontested_effects']+=sum(effects.get(token,()))
                else:
                    counts['externally_reproposed']+=1
            else:
                counts['failed_steps']+=1
        for counts in returns.values():
            totals.update(counts)
        totals.update(self.claim_counts)
        totals['omitted_packets']=sum(self.omissions.values())
        totals['omitted_valid_packets']=sum(n for t,n in self.omissions.items() if
                                              self.rewards.get(t,(None,None))[1]=='accepted')
        return returns,totals


def load_policy(folder,baked,training_bake=None):
    if read(folder/'training.json').get('objective')=='native_receipt_value':
        from receipt_value import ReceiptChoice
        if training_bake:
            raise ValueError('receipt values require their frozen Bake catalog')
        return ReceiptChoice(folder,baked)
    from train_layout_bandit import LearnedChoice
    return LearnedChoice(folder,baked,training_bake)


def rollout(root,donor,binary,weights,baked,out,name,seed,omit,explore,policy=None,attach=False,run_recall=False,prefix=None,field_reader=None):
    actor=load_actor(weights,True)
    folder=root/name
    issuer=CreditIssuer(actor,read(donor/'program.json'),read(folder/'program.json'),baked,
                        omit=omit,explore=explore,seed=seed,policy=policy,attach=attach)
    issuer.field_reader=field_reader
    if explore and name not in read(baked/'study.json')['training']:
        raise ValueError('exploration training must use training programs')
    if digest(weights)!=read(baked/'study.json')['root_weights']:
        raise ValueError('root Actor differs from the trained Bake catalog')
    ref=read(folder/'capture.json')
    manifest=read(root/'manifest.json')
    rename=1703+next((r['seed'] for r in manifest if r['directory']==name),0)
    accepted=Counter()
    committed=Counter()
    seen=set()
    def observe(frame):
        for req in frame['accepted']:
            if req['run']!=frame['run']-1 or req['token'] in seen:
                raise ValueError('invalid sealed commit receipt')
            seen.add(req['token'])
            key=req['run'],req['rule']
            committed[key]+=1
            if req['token']<RESIDUAL:
                accepted[key]+=1
    with TemporaryDirectory() as tmp:
        spec=Path(tmp)/'layouts.json'
        spec.write_text(json.dumps(issuer.receiver_layouts(),separators=(',',':')))
        result=execute(binary,folder/'program.json',actor,rename,assist=True,prefix_policy=prefix or Policy(32),
                       graph_issuer=issuer,layout_file=spec,audit_ept=True,frame_observer=observe if run_recall else None)
    for key,target in [('source_schedule','schedule'),('rhs_by_run','rhs'),('writes_by_run','writes'),
                       ('resume_audit','resumes'),('event_audit','events')]:
        if result.pop(key)!=ref[target]:
            raise ValueError('source audit differs in '+target)
    if result['state_sha']!=ref['state_sha']:
        raise ValueError('source state changed')
    recovery=prefix.recovery if prefix else None
    if recovery is None:
        del result['partial_proof_counts']
    elif not any(c.get('recovery_scored',0) for c in result['partial_proof_counts'].values()):
        raise ValueError('recovery head did not score any reads')
    per_root,counts=issuer.credit(result['ept'])
    if result['issued']+counts['omitted_packets']!=issuer.counts['root_packets']:
        raise ValueError('external packet attribution differs')
    if counts['accepted']!=result['layouts']['counts']['accepted_steps']:
        raise ValueError('step outcomes differ from native seal')
    out.mkdir(exist_ok=True,parents=True)
    backend=result['layouts']['counts']
    completed={int(k):v for k,v in backend['completed_layouts'].items()}
    held_issued=0
    held_complete=0
    for u,index in issuer.portable.items():
        n=completed.get(index,0)
        if n:
            issuer.finished_units.add(u)
            issuer.sizes[len(issuer.layouts[u])]['complete']+=n
        if u in issuer.withheld:
            held_issued+=backend['issued_layouts'].get(str(index),0)
            held_complete+=n
    if explore and held_issued:
        raise ValueError('withheld layout was explored')
    if explore:
        # The episode ends at the original source schedule. A still-waiting
        # layout receives only its realized prefix credit, through that boundary.
        rows=[]
        for token,(menu,context,action,probability,baseline,run) in issuer.log.items():
            counts_for_root=per_root.get(token,{})
            rows.append([menu,context,action,probability,baseline,counts_for_root,run])
        with gzip.open(out/f'{name}-{seed}.json.gz','wt') as stream:
            json.dump(dict(menus=list(issuer.menus),rows=rows),stream,separators=(',',':'))
    stem=f'{name}-{seed}' if explore else name
    report=dict(mode='native assist',program=name,tape=digest(folder/'tape.json'),binary=digest(binary),
                actor=digest(weights),policy=policy.checkpoint if policy else None,scorer=digest(baked/'shared.pt'),reader=digest(baked/'boundary.pt'),
                catalog=digest(baked/'catalog.json'),omit=omit,attach=attach,explore=explore,seed=seed,
                withheld_layouts=len(issuer.withheld),held_issued=held_issued,held_complete=held_complete,reference_commits=ref['matches'],issuer=issuer.report(),credit=counts,execution=result)
    if recovery is not None:
        report['recovery']=dict(checkpoint=recovery.checkpoint,margin_only=recovery.margin_only,cut=recovery.cut,
                                budget=recovery.budget,refinements=recovery.refinements)
    if field_reader is not None:
        if not issuer.counts['routed_reads']:
            raise ValueError('loaded field reader never ran')
        report['field_reader']=field_reader.checkpoint
    if prefix is not None:
        report['root_budget']=prefix.top_k
    if prefix is not None and prefix.read_order!='source':
        report['read_order']=prefix.read_order
    ordinary=ref.get('residual_candidates')
    live=result['residual_candidates']
    if ordinary is not None and live is not None:
        report['candidate_work']=dict(reference=ordinary,assist=live,avoided=ordinary-live,
                                      fraction_saved=(ordinary-live)/ordinary if ordinary else None)
    if run_recall:
        reference=Counter((req['run'],req['rule']) for req in read(folder/'tape.json')['requests'])
        if reference!=committed or sum(accepted.values())!=result['counts']['accepted']:
            raise ValueError('per-Run commit attribution differs from reference')
        report['recall_by_rule_run']=[(r,rid,accepted[r,rid],n) for (r,rid),n in sorted(reference.items())]
        by_run=defaultdict(Counter)
        for (r,rid),n in reference.items():
            by_run[r]['signed']+=accepted[r,rid]
            by_run[r]['required']+=n
        report['recall_by_nonempty_run']=[(r,v['signed'],v['required']) for r,v in sorted(by_run.items())]
    (out/(stem+'.json')).write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','donor','binary','weights','baked','out'):
        p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    p.add_argument('--seeds',nargs='+',type=int,default=[1703])
    p.add_argument('--omit',action='store_true')
    p.add_argument('--policy',type=Path)
    p.add_argument('--field-reader',type=Path)
    p.add_argument('--training-bake',type=Path)
    p.add_argument('--recovery',type=Path)
    p.add_argument('--root-budget',type=int,default=32,help='maximum prefixes per rule, anchor role and depth')
    p.add_argument('--read-order',choices=('source','connected','delta'))
    p.add_argument('--margin-only',action='store_true')
    p.add_argument('--run-recall',action='store_true')
    p.add_argument('--exclusive',action='store_true')
    p.add_argument('--attach',action='store_true')
    p.add_argument('--explore',action='store_true')
    args=p.parse_args()
    torch.set_num_threads(1)
    policy=None
    reader=None
    if args.field_reader:
        from field_wiring import FieldReader
        reader=FieldReader(args.field_reader,args.baked)
    prefix=None
    if args.recovery:
        from prefix_recovery import Recovery
        prefix=Policy(args.root_budget,recovery=Recovery(args.recovery,args.weights,margin_only=args.margin_only),read_order=args.read_order)
    elif args.margin_only:
        p.error('--margin-only requires a recovery head')
    elif args.read_order or args.root_budget!=32:
        prefix=Policy(args.root_budget,read_order=args.read_order)
    if args.policy:
        if args.explore: raise ValueError('frozen deployment requires a separate exploration arm')
        policy=load_policy(args.policy,args.baked,args.training_bake)
    for name in args.cases:
        if args.exclusive:
            if args.explore:
                raise ValueError('the exploration dataset requires native assist')
            args.out.mkdir(exist_ok=True,parents=True)
            def build(actor,donor,target,baked,native):
                issuer=CreditIssuer(actor,donor,target,baked,omit=args.omit,explore=False,
                                    seed=1703,policy=policy,attach=args.attach)
                issuer.field_reader=reader
                return issuer
            evaluate(args.root,read(args.donor/'program.json'),args.binary,args.weights,args.baked,name,
                     args.out/(name+'.json'),False,True,exclusive=True,issuer_factory=build,prefix=prefix)
            continue
        for seed in args.seeds:
            rollout(args.root,args.donor,args.binary,args.weights,args.baked,args.out,name,seed,
                    args.omit,args.explore,policy=policy,attach=args.attach,run_recall=args.run_recall,prefix=prefix,field_reader=reader)
