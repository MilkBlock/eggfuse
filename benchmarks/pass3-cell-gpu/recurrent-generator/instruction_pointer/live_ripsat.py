"""Run a shared graph scorer and boundary reader against the ordinary named native verifier."""
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass,field
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import perf_counter

import torch

from alternate_proofs import digest
from anchor_set_audit import load_actor
from higher_cell import read
from online import SourcePanic,execute
from prefix_policy import Policy
from ripsat_boundary import BoundaryReader,fields
from ripsat_layout import signatures
from ripsat_policy import CellScorer,root_context
from ripsat_replay import unpack
from side_boundary import address


@dataclass
class Instance:
    unit:int
    boundary:list
    group:int=0
    sent:dict=field(default_factory=dict)
    returns:dict=field(default_factory=dict)


class GraphIssuer:
    @torch.no_grad()
    def __init__(self,actor,donor,target,baked,native=False):
        self.native=native
        study=read(baked/'study.json')
        report=read(baked/'boundary.json')
        if (digest(baked/'catalog.json')!=study['catalog_sha'] or report['catalog']!=study['catalog_sha']
            or digest(baked/'shared.pt')!=study['weights'] or report['scorer']!=study['weights']
            or digest(baked/'boundary.pt')!=report['weights']):
            raise ValueError('catalog and checkpoint identities disagree')
        self.layouts=unpack(read(baked/'catalog.json'))
        fixed=read(baked/'fixed.json')
        if (fixed['catalog']!=study['catalog_sha'] or fixed['scorer']!=study['weights'] or
            fixed['root_weights']!=study['root_weights'] or digest(baked/'codes.pt')!=fixed['codes'] or
            fixed['signatures']!=signatures(donor)):
            raise ValueError('baked layout data differs from the frozen model or program')
        tensors=torch.load(baked/'codes.pt',weights_only=True)
        self.codes=tensors['codes']
        self.model=CellScorer(actor.width).eval()
        self.model.load_state_dict(torch.load(baked/'shared.pt',weights_only=True))
        self.reader=BoundaryReader(actor.width).eval()
        self.field_reader=None
        self.reader.load_state_dict(torch.load(baked/'boundary.pt',weights_only=True))
        target_ids={v:i for i,v in enumerate(signatures(target))}
        self.rule={i:target_ids[s] for i,s in enumerate(signatures(donor)) if s in target_ids}
        tables={t['name']:i for i,t in enumerate(target['recipe']['tables'])}
        self.roles={}
        self.groups={}
        self.exports={}
        self.choices=defaultdict(list)
        for u,l in enumerate(self.layouts):
            if any(r not in self.rule for r,_,_ in l):
                continue
            self.roles[u]=[(tables[t],tensors['roles'][k]) for t,k in fixed['inputs'][u]]
            self.choices[self.rule[l[0][0]]].append(u)
            groups=defaultdict(list)
            exports=defaultdict(set)
            for i,(_,g,wires) in enumerate(l):
                groups[g].append(i)
                for parent,pc in wires:
                    if parent>=0:
                        exports[parent].add(pc)
            self.groups[u]=dict(groups)
            self.exports[u]=dict(exports)
        self.portable={u:i for i,u in enumerate(self.groups)}
        self.instances=[]
        self.counts=Counter()
        self.sizes=defaultdict(Counter)
        self.issued_units=set()
        self.finished_units=set()
        self.seconds=0.

    def receiver_layouts(self):
        return [[(self.rule[r],group,wires) for r,group,wires in self.layouts[u]] for u in self.portable]

    def report(self):
        return dict(counts=self.counts,steps=self.sizes,distinct_issued=len(self.issued_units),
                    distinct_complete=len(self.finished_units),outstanding=len(self.instances),seconds=self.seconds)

    def choose_layout(self,req,options,context):
        scores=self.model(context.expand(len(options),-1),self.codes[options])[:,1]
        k=int(scores.argmax())
        return options[k] if scores[k]>0 else None

    def select(self,req,options,history,domains):
        if not options:
            return None
        refs=req['parents']
        prior=[tuple(history.visible[address(p)]['hashes']) for p in refs]
        context=root_context(prior,self.codes.shape[1])
        self.counts['root_decisions']+=1
        u=self.choose_layout(req,options,context)
        if u is None:
            return None
        return self.bind_layout(req,u,history,domains)

    def bind_layout(self,req,u,history,domains):
        refs=req['parents']
        layout=self.layouts[u]
        points={}
        for (_,slot),p in zip(layout[0][2],refs,strict=True):
            if slot in points and p!=points[slot]:
                self.counts['conflicting_root_slot']+=1
                return None
            points[slot]=p
        for slot,(table,role) in enumerate(self.roles[u]):
            if slot in points:
                continue
            ports=domains.get(table)
            if not ports:
                self.counts['empty_input_type']+=1
                return None
            prior=[tuple(history.visible[address(points[j])]['hashes']) for j in sorted(points)]
            ctx=torch.cat((self.codes[u],role,root_context(prior,self.codes.shape[1])))
            rows=[p.hashes for p in ports]
            keys,comparison=fields(prior,rows,self.codes.shape[1])
            scores=self.reader(ctx[None],keys[None],comparison[None])[0]
            j=int(scores.argmax())
            if self.field_reader is not None and self.field_reader.routes.has_links(u,slot):
                prior_slots=dict(zip(sorted(points),prior,strict=True))
                adjusted=int((scores+self.field_reader.adjustment(u,slot,prior_slots,rows)).argmax())
                self.counts['routed_reads']+=1
                self.counts['routed_candidate_scores']+=len(ports)
                self.counts['changed_port_choices']+=int(j!=adjusted)
                j=adjusted
            alias,pc=ports[j].address
            points[slot]=dict(address=dict(token=history.inverse[alias],op=pc),version=ports[j].version)
            self.counts['named_independent_slots']+=1
            self.counts['pointer_scores']+=len(ports)
        return Instance(u,[points[j] for j in range(len(points))])

    @torch.no_grad()
    def batch(self,frame,history,snap,roots,next_token):
        started=perf_counter()
        issued=[]
        keep=[]
        accepted={r['token'] for r in frame['accepted']}
        scheduled=set(snap.rules)
        def allowed(u,g):
            l=self.layouts[u]
            return all(self.rule[l[i][0]] in scheduled for i in self.groups[u][g])
        def emit(inst,i):
            nonlocal next_token
            rid,_,wires=self.layouts[inst.unit][i]
            parents=[inst.boundary[slot] if owner<0 else inst.returns[owner,slot] for owner,slot in wires]
            issued.append(dict(rule=self.rule[rid],run=snap.run,token=next_token,parents=parents))
            inst.sent[i]=next_token
            next_token+=1
        for inst in self.instances:
            u=inst.unit
            if inst.sent:
                self.counts['verified_expansion_steps']+=sum(t in accepted for i,t in inst.sent.items() if i!=0)
                if not all(t in accepted for t in inst.sent.values()):
                    self.counts['group_rejected']+=1
                    continue
                group=inst.sent
                inst.sent={}
                inst.group+=1
                if inst.group==len(self.groups[u]):
                    self.sizes[len(self.layouts[u])]['complete']+=1
                    self.finished_units.add(u)
                    continue
                missing=False
                for step,token in group.items():
                    for pc in self.exports[u].get(step,()):
                        row=history.visible.get((token,pc))
                        if row is None:
                            missing=True
                            break
                        inst.returns[step,pc]=dict(address=dict(token=token,op=pc),version=row['version'])
                if missing:
                    self.counts['missing_return']+=1
                    continue
            if allowed(u,inst.group):
                for step in self.groups[u][inst.group]:
                    emit(inst,step)
            keep.append(inst)
        domains=defaultdict(list)
        for port in snap.ports:
            domains[port.table].append(port)
        opts={rid:[u for u in self.choices[rid] if allowed(u,0)] for rid in {r['rule'] for r in roots}}
        for req in roots:
            inst=self.select(req,opts[req['rule']],history,domains)
            if inst is None:
                continue
            u=inst.unit
            self.sizes[len(self.layouts[u])]['issued']+=1
            self.issued_units.add(u)
            if self.native:
                req['graph']=dict(layout=self.portable[u],boundary=inst.boundary)
                continue
            inst.sent[0]=req['token']
            for step in self.groups[u][0][1:]:
                emit(inst,step)
            keep.append(inst)
        self.instances=keep
        self.counts['materialized_steps']+=len(issued)
        self.counts['root_packets']+=len(roots)
        self.seconds+=perf_counter()-started
        return issued,next_token


def evaluate(root,donor,binary,weights,baked,name,out,control,native,exclusive=False,issuer_factory=GraphIssuer,prefix=None):
    if digest(weights)!=read(baked/'study.json')['root_weights']:
        raise ValueError('root Actor checkpoint differs from training')
    folder=root/name
    actor=load_actor(weights,True)
    started=perf_counter()
    issuer=None if control else issuer_factory(actor,donor,read(folder/'program.json'),baked,native)
    setup=perf_counter()-started
    seed=next((r['seed'] for r in read(root/'manifest.json') if r['directory']==name),0)
    with TemporaryDirectory() as tmp:
        layouts=None
        if native and issuer:
            layouts=Path(tmp)/'layouts.json'
            layouts.write_text(json.dumps(issuer.receiver_layouts(),separators=(',',':')))
        def live(limit=None):
            return execute(binary,folder/'program.json',actor,1703+seed,assist=not exclusive,prefix_policy=prefix or Policy(32),
                           graph_issuer=issuer,layout_file=layouts,audit_ept=not exclusive,run_limit=limit)
        failure=None
        try:
            run=live()
        except SourcePanic as error:
            if not exclusive:
                raise
            failure=dict(run=error.run,charged=error.charged)
            issuer=None if control else issuer_factory(actor,donor,read(folder/'program.json'),baked,native)
            run=live(error.run-1)
            if run['runs']!=error.run-1:
                raise ValueError('could not reproduce prefix before panic')
    if exclusive:
        ref=read(folder/'capture.json')
        common=0
        for i,schedule in enumerate(run['source_schedule']):
            if (i>=ref['runs'] or schedule!=ref['schedule'][i] or run['writes_by_run'][i]!=ref['writes'][i]
                or run['rhs_by_run'][i]!=ref['rhs'][i]):
                break
            common+=1
        field_audit={}
        if getattr(issuer,'field_reader',None) is not None:
            if not issuer.counts['routed_reads']:
                raise ValueError('loaded field reader never ran on exclusive prefix')
            field_audit=dict(field_reader=issuer.field_reader.checkpoint,issuer=issuer.report())
        out.write_text(json.dumps(dict(case=name,mode='exclusive',binary=digest(binary),actor=digest(weights),
            catalog=digest(baked/'catalog.json'),common_runs=common,reference_runs=ref['runs'],
            final_equal=failure is None and run['state_sha']==ref['state_sha'],failure=failure,
            independent_search_calls=run['independent_search_calls'],paid=run['issued'],
            layouts=run.get('layouts'),**field_audit),indent=2)+'\n')
        return
    if native and issuer:
        backend=run['layouts']['counts']
        completed={int(u):n for u,n in backend['completed_layouts'].items()}
        for uid,index in issuer.portable.items():
            if index in completed:
                issuer.finished_units.add(uid)
                issuer.sizes[len(issuer.layouts[uid])]['complete']+=completed[index]
        if backend['signed_layouts']!=sum(s['issued'] for s in issuer.sizes.values()):
            raise ValueError('native and policy graph issue counts differ')
    wall=perf_counter()-started
    ref=read(folder/'capture.json')
    for a,b in [('source_schedule','schedule'),('rhs_by_run','rhs'),('writes_by_run','writes'),
                ('resume_audit','resumes'),('event_audit','events')]:
        if run.pop(a)!=ref[b]:
            raise ValueError('native source audit differs in '+b)
    if run['state_sha']!=ref['state_sha']:
        raise ValueError('native final state differs')
    exact=json.loads(subprocess.check_output([binary,'reference',folder/'program.json','-','audit','--ept']))
    ledger=run['ept']
    if (ledger['ledger_sha256']!=exact['ept']['ledger_sha256'] or
        [sum(x) for x in zip(ledger['signed_external'],ledger['signed_internal'],ledger['uncredited'],strict=True)]!=exact['ept']['uncredited']):
        raise ValueError('effective operation ledger differs')
    del run['partial_proof_counts']
    if issuer and (not issuer.finished_units or run['issued']!=issuer.counts['root_packets']+issuer.counts['materialized_steps']):
        raise ValueError('joint issuance did not complete or request counts differ')
    out.write_text(json.dumps(dict(case=name,mode='native assist',transport='signed graph' if native else 'separate requests',binary=digest(binary),actor=digest(weights),
        catalog=digest(baked/'catalog.json'),scorer=digest(baked/'shared.pt'),reader=digest(baked/'boundary.pt'),
        reference_commits=ref['matches'],setup_seconds=setup,wall_seconds=wall,
        issuer=issuer.report() if issuer else None,execution=run),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','donor','binary','weights','baked','out'):
        p.add_argument(k,type=Path)
    p.add_argument('--case',required=True)
    p.add_argument('--control',action='store_true')
    p.add_argument('--native',action='store_true')
    p.add_argument('--exclusive',action='store_true')
    a=p.parse_args()
    torch.set_num_threads(1)
    evaluate(a.root,read(a.donor/'program.json'),a.binary,a.weights,a.baked,a.case,a.out,a.control,a.native,a.exclusive)
