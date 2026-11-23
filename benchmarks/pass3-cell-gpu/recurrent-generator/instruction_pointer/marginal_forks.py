"""Collect full-program causal targets for a single named higher-Cell decision."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory

import torch

from alternate_proofs import digest
from anchor_set_audit import load_actor
from higher_cell import read
from layout_credit import CreditIssuer, load_policy
from layout_credit_report import verify
from online import RESIDUAL, execute
from prefix_policy import Policy
from prefix_recovery import Recovery


def fingerprint(hash_state, obj):
    hash_state.update(json.dumps(obj, separators=(',', ':'), sort_keys=True).encode())
    hash_state.update(b'\n')


class InterventionIssuer(CreditIssuer):
    def __init__(self, *args, original=None, stop=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.original = original
        self.stop = stop
        self.decisions = {}
        self.history_hash = hashlib.sha256()
        self.bound = {}
        self.reuse = False
        self.hit = False

    def bind_layout(self, req, uid, history, domains):
        if self.reuse:
            return self.original.bound[req['token']]
        instance = super().bind_layout(req, uid, history, domains)
        if self.original is None:
            self.bound[req['token']] = instance
        return instance

    def batch(self, frame, history, snap, roots, next_token):
        fingerprint(self.history_hash, [frame[k] for k in ('run', 'rules', 'epoch', 'updates', 'retired',
                                                           'accepted', 'repair_events', 'layout_feedback')])
        return super().batch(frame, history, snap, roots, next_token)

    def choose_layout(self, req, options, context):
        token = req['token']
        fingerprint(self.history_hash, req)
        before = self.history_hash.hexdigest()
        logged = self.original.decisions.get(token) if self.original is not None else None
        self.reuse = logged is not None and logged[0] == before
        if self.reuse:
            uid = logged[1]
        else:
            eligible = [i for i in options if i not in self.withheld]
            uid = super().choose_layout(req, eligible, context) if eligible else None
        if self.original is None:
            self.decisions[token] = (before, uid, req['run'], context.tolist())
        if token == self.stop:
            if self.hit or logged is None or logged[0] != before or uid is None:
                raise ValueError('unmatched single-decision intervention')
            self.hit = True
            uid = None
        fingerprint(self.history_hash, uid)
        return uid


def aligned(run):
    rows = run['ept'].pop('origins')
    signed = {ordinal for ordinal, (token, _) in enumerate(rows, 1)
              if token is not None and 0 < token < RESIDUAL}
    effects = tuple(count for _, count in rows)
    if (len(signed) != run['counts']['accepted'] or
            len(rows) != len(signed)+run['assist']['residual_commits'] or
            sum(effects[i-1] for i in signed) != sum(run['ept']['signed_external']+run['ept']['signed_internal'])):
        raise ValueError('source-ordinal and EPT totals disagree')
    return signed, effects


def collect(root, donor, binary, weights, baked, policy, recovery, gold, out, name, draws, seed):
    folder = root/name
    study = read(baked/'study.json')
    if study['training'].get(name) != digest(folder/'tape.json') or study['root_weights'] != digest(weights):
        raise ValueError('only the frozen training corpus may supply interventions')
    program = read(folder/'program.json')
    reference = read(folder/'capture.json')
    rename = 1703+next(r['seed'] for r in read(root/'manifest.json') if r['directory']==name)
    actor = load_actor(weights, True)
    choice = load_policy(policy, baked)
    prefix = Policy(32, recovery=Recovery(recovery, weights))
    metadata = dict(program=name, program_sha=digest(folder/'program.json'), actor=digest(weights),
                    binary=digest(binary), catalog=study['catalog_sha'], policy=choice.checkpoint,
                    recovery=prefix.recovery.checkpoint, tape=study['training'][name], draws=draws, seed=seed)
    def episode(spec, original=None, token=None):
        issuer = InterventionIssuer(actor,donor,program,baked,omit=True,explore=False,seed=rename,
                                    policy=choice,attach=True,original=original,stop=token)
        if not spec.exists():
            spec.write_text(json.dumps(issuer.receiver_layouts(),separators=(',',':')))
        run = execute(binary,folder/'program.json',actor,rename,assist=True,audit_origins=True,
                      prefix_policy=prefix,graph_issuer=issuer,layout_file=spec)
        if token is not None and not issuer.hit:
            raise ValueError('intervention was not reached')
        for src, dst in [('source_schedule','schedule'),('rhs_by_run','rhs'),('writes_by_run','writes'),
                         ('resume_audit','resumes'),('event_audit','events')]:
            if run[src] != reference[dst]:
                raise ValueError('source execution changed in '+dst)
        verify(dict(execution=run,reference_commits=reference['matches']),gold)
        signed, effects = aligned(run)
        credits, _ = issuer.credit(run['ept'])
        return issuer,signed,effects,credits,run['issued']
    with TemporaryDirectory() as tmp:
        spec = Path(tmp)/'layouts.json'
        base, signed, effects, credits, paid = episode(spec)
        pools = defaultdict(list)
        for token, (_,uid,_,_) in base.decisions.items():
            if uid is None:
                continue
            c = credits.get(token, {})
            if c.get('owned_valid') or c.get('uncontested'):
                category = 'locally_credited'
            elif c.get('attempts'):
                category = 'other_attempt'
            else:
                category = 'no_child_attempt'
            pools[category].append(token)
        rng = random.Random(seed)
        sample = []
        for category, tokens in sorted(pools.items()):
            n = min(len(tokens), draws)
            sample.extend((token,category,n/len(tokens)) for token in rng.sample(tokens,n))
        metadata.update(populations={k:len(v) for k,v in pools.items()}, signed=len(signed),paid=paid,
                        operations=sum(effects[i-1] for i in signed), state=reference['state_sha'])
        out.mkdir(parents=True,exist_ok=True)
        path = out/(name+'.json')
        data = dict(metadata=metadata,rows=[])
        if path.exists():
            saved = read(path)
            if saved['metadata'] != metadata:
                raise ValueError('existing interventions belong to another experiment')
            data = saved
        for index,(token,category,prob) in enumerate(sample):
            before,uid,run,ctx = base.decisions[token]
            if index < len(data['rows']):
                row = data['rows'][index]
                if (row['token'],row['before'],row['layout']) != (token,before,uid):
                    raise ValueError('incompatible resumed decision')
                continue
            _, alt, alt_effects, _, alt_paid = episode(spec,base,token)
            if alt_effects != effects:
                raise ValueError('effective source operations differ by ordinal')
            added, lost = sorted(signed-alt), sorted(alt-signed)
            data['rows'].append(dict(token=token,before=before,layout=uid,size=len(base.layouts[uid]),
                run=run,context=ctx,stratum=category,probability=prob,local=credits.get(token,{}),
                added=added,lost=lost,net_signed=len(added)-len(lost),
                net_operations=sum(effects[i-1] for i in added)-sum(effects[i-1] for i in lost),
                saved_packets=alt_paid-paid))
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(data,separators=(',',':'))+'\n')
            temp.replace(path)
            print(name,index+1,len(sample),category,len(added),len(lost),alt_paid-paid,flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('root','donor','binary','weights','baked','policy','recovery','gold','out'):
        p.add_argument(key,type=Path)
    p.add_argument('--case',required=True)
    p.add_argument('--draws',type=int,default=4,help='single-root interventions per stratum')
    p.add_argument('--seed',type=int,default=1703)
    a = p.parse_args()
    torch.set_num_threads(1)
    collect(a.root,read(a.donor/'program.json'),a.binary,a.weights,a.baked,a.policy,a.recovery,
            read(a.gold/(a.case+'.json')),a.out,a.case,a.draws,a.seed)
