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


def compare(folder,donor,binary,weights,baked,audits,seed):
    results=[]
    records={arm:read(audits/f'{folder.name}-{arm}.json') for arm in ('control','native')}
    for arm,record in records.items():
        if any(record[k]!=digest(path) for k,path in [('binary',binary),('actor',weights),
                ('scorer',baked/'shared.pt'),('reader',baked/'boundary.pt'),('catalog',baked/'catalog.json')]):
            raise ValueError('timing inputs differ from the work audit')
    for turn in range(4):
        pair={}
        order=['exact','control','native','oracle']
        for arm in (reversed(order) if turn%2 else order):
            if arm not in records:
                pair[arm]=measure(folder,binary,weights,seed,arm,False)
                continue
            start=perf_counter()
            actor=load_actor(weights,True)
            issuer=None if arm=='control' else GraphIssuer(actor,donor,read(folder/'program.json'),baked,True)
            with TemporaryDirectory() as tmp:
                layout_file=None
                if issuer:
                    layout_file=Path(tmp)/'layouts.json'
                    layout_file.write_text(json.dumps(issuer.receiver_layouts(),separators=(',',':')))
                r=execute(binary,folder/'program.json',actor,seed,assist=True,audit=False,
                          graph_issuer=issuer,layout_file=layout_file,prefix_policy=Policy(32))
            wall=perf_counter()-start
            expected=records[arm]['execution']
            if any(r.get(k)!=expected.get(k) for k in ('issued','state_sha','counts','layouts','runs')):
                raise ValueError('timed execution diverged from signed operation audit')
            e=expected['ept']
            ops=sum(e['signed_external']+e['signed_internal'])
            pair[arm]=dict(wall=wall,signed_ops=ops,eps=ops/wall,root=r['network_seconds'],
                           graph=issuer.seconds if issuer else 0,verify=r['native_verify_seconds'],
                           residual=r['assist']['exact_seconds'])
        results.append(pair)
    return dict(binary=digest(binary),weights=digest(weights),reader=digest(baked/'boundary.pt'),
                pairs=results,median_eps={k:median(p[k]['eps'] for p in results) for k in records},
                native_eps_wins=sum(p['native']['eps']>p['control']['eps'] for p in results))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','donor','binary','weights','baked','audits','out'):
        p.add_argument(k,type=Path)
    p.add_argument('--cases',required=True,nargs='+')
    a=p.parse_args()
    torch.set_num_threads(1)
    seeds={s['directory']:s['seed'] for s in read(a.root/'manifest.json')}
    donor=read(a.donor/'program.json')
    reports={}
    for name in a.cases:
        reports[name]=compare(a.root/name,donor,a.binary,a.weights,a.baked,a.audits,1703+seeds.get(name,0))
        a.out.write_text(json.dumps(reports,indent=2)+'\n')
