"""Time the actual joint issuer and receiver with the signed operations from their audited runs."""
import argparse
import json
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

import torch

from anchor_set_audit import load_actor
from assist_cost import measure
from alternate_proofs import digest
from higher_cell import read
from live_ripsat import GraphIssuer
from online import execute
from prefix_policy import Policy


def compare(folder,donor,binary,weights,baked,audits,seed,learned=None,base_bake=None,base_policy=None,additional=None,recovery_dir=None,field_dir=None):
    results=[]
    if learned:
        from layout_credit import CreditIssuer,load_policy
        arms=('original','refit') if base_bake else ('attach','rl')
        if additional:
            arms=(*arms,'additional')
        records={arm:read(audits/arm/(folder.name+'.json')) for arm in arms}
    else:
        arms=('control','native')
        records={arm:read(audits/f'{folder.name}-{arm}.json') for arm in arms}
    def catalog(arm):
        return base_bake if arm=='original' else baked
    for arm,record in records.items():
        if any(record[k]!=digest(path) for k,path in [('binary',binary),('actor',weights),
                ('scorer',baked/'shared.pt'),('reader',baked/'boundary.pt'),('catalog',catalog(arm)/'catalog.json')]):
            raise ValueError('timing inputs differ from the work audit')
    for turn in range(4):
        pair={}
        order=['exact',*arms,'oracle']
        for arm in (reversed(order) if turn%2 else order):
            if arm not in records:
                pair[arm]=measure(folder,binary,weights,seed,arm,False)
                continue
            start=perf_counter()
            actor=load_actor(weights,True)
            if learned:
                checkpoint=base_policy if arm=='original' else learned
                if arm=='additional':
                    checkpoint=additional
                policy=None if arm=='attach' else load_policy(checkpoint,catalog(arm))
                if records[arm]['policy']!=(policy.checkpoint if policy else None):
                    raise ValueError('timed layout policy differs from the audit')
                issuer=CreditIssuer(actor,donor,read(folder/'program.json'),catalog(arm),omit=True,
                                    attach=True,seed=1703,explore=False,policy=policy)
                if records[arm].get('field_reader'):
                    from field_wiring import FieldReader
                    if field_dir is None:
                        raise ValueError('field checkpoint required by timed audit')
                    issuer.field_reader=FieldReader(field_dir,catalog(arm))
                    if issuer.field_reader.checkpoint!=records[arm]['field_reader']:
                        raise ValueError('timed field pointer differs from work audit')
            else:
                issuer=None if arm=='control' else GraphIssuer(actor,donor,read(folder/'program.json'),baked,True)
            prefix=Policy(32)
            settings=records[arm].get('recovery')
            if settings:
                from prefix_recovery import Recovery
                recovery=Recovery(recovery_dir,weights,margin_only=settings['margin_only'])
                if (recovery.checkpoint,recovery.cut,recovery.budget)!=(settings['checkpoint'],settings['cut'],settings['budget']):
                    raise ValueError('recovery head differs from audited execution')
                prefix=Policy(32,recovery=recovery)
            with TemporaryDirectory() as tmp:
                layout_file=None
                if issuer:
                    layout_file=Path(tmp)/'layouts.json'
                    layout_file.write_text(json.dumps(issuer.receiver_layouts(),separators=(',',':')))
                r=execute(binary,folder/'program.json',actor,seed,assist=True,audit=False,
                          graph_issuer=issuer,layout_file=layout_file,prefix_policy=prefix)
            wall=perf_counter()-start
            expected=records[arm]['execution']
            if any(r.get(k)!=expected.get(k) for k in ('issued','state_sha','counts','layouts','runs')):
                raise ValueError('timed execution diverged from signed operation audit')
            if issuer and records[arm].get('field_reader') and issuer.counts!=records[arm]['issuer']['counts']:
                raise ValueError('timed field read counts differ from audited issuance')
            e=expected['ept']
            ops=sum(e['signed_external']+e['signed_internal'])
            pair[arm]=dict(wall=wall,signed_ops=ops,eps=ops/wall,root=r['network_seconds'],
                           graph=issuer.seconds if issuer else 0,verify=r['native_verify_seconds'],
                           residual=r['assist']['exact_seconds'])
        results.append(pair)
    return dict(binary=digest(binary),weights=digest(weights),reader=digest(baked/'boundary.pt'),
                pairs=results,median_eps={k:median(p[k]['eps'] for p in results) for k in records},
                **{arm+'_eps_wins':sum(p[arm]['eps']>p[arms[0]]['eps'] for p in results) for arm in arms[1:]})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','donor','binary','weights','baked','audits','out'):
        p.add_argument(k,type=Path)
    p.add_argument('--recovery-dir',type=Path)
    p.add_argument('--field-reader',type=Path)
    p.add_argument('--policy',type=Path)
    p.add_argument('--additional-policy',type=Path)
    p.add_argument('--base-bake',type=Path)
    p.add_argument('--base-policy',type=Path)
    p.add_argument('--cases',required=True,nargs='+')
    a=p.parse_args()
    if a.additional_policy and not a.policy:
        p.error('additional selector requires a primary policy')
    if bool(a.base_bake)!=bool(a.base_policy) or (a.base_bake and not a.policy):
        p.error('comparison across catalogs requires base and new checkpoints')
    torch.set_num_threads(1)
    seeds={s['directory']:s['seed'] for s in read(a.root/'manifest.json')}
    donor=read(a.donor/'program.json')
    reports={}
    for name in a.cases:
        reports[name]=compare(a.root/name,donor,a.binary,a.weights,a.baked,a.audits,1703+seeds.get(name,0),a.policy,a.base_bake,a.base_policy,a.additional_policy,a.recovery_dir,a.field_reader)
        a.out.write_text(json.dumps(reports,indent=2)+'\n')
