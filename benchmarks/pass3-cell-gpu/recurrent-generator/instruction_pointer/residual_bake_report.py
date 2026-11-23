"""Compare oracle trace opportunities and checked live outcomes for two Bake generations."""
import argparse
from collections import Counter
from pathlib import Path
import json

from alternate_proofs import digest
from higher_cell import read
from layout_credit_report import verify
from residual_layouts import analyze
from ripsat_layout import signatures
from ripsat_replay import unpack
from train_ripsat import layout_id


def audit(root,donor,experiment,base,gold,cases):
    original=unpack(read(base/'catalog.json'))
    extended=unpack(read(experiment/'expanded/catalog.json'))
    if extended[:len(original)]!=original:
        raise ValueError('catalog extension changes prefix')
    sources=signatures(donor)
    reports={}
    for name in cases:
        trace=experiment/name
        capture=read(trace/'opportunity.json')
        reachable={}
        for tag,catalog in [('original',original),('expanded',extended)]:
            reachable[tag],_=analyze(trace,donor,set(catalog),max(map(len,catalog)))
        if capture['reach']!=reachable['original']['reach']:
            raise ValueError('base reachability changed')
        local=set(signatures(read(root/name/'program.json')))
        arms={}
        for tag,catalog in [('original',original),('expanded',extended),('refit',extended)]:
            report=read(experiment/'final'/tag/(name+'.json'))
            verify(report,read(gold/(name+'.json')))
            if report['catalog']!=digest((base if tag=='original' else experiment/'expanded')/'catalog.json'):
                raise ValueError('audit uses the wrong layout identities')
            units=[u for u,l in enumerate(catalog) if all(sources[r] in local for r,_,_ in l)]
            run=report['execution']
            native=run['layouts']['counts']
            groups={}
            for kind in ('issued','completed'):
                counts=Counter()
                for i,n in native[kind+'_layouts'].items():
                    u=units[int(i)]
                    held=int(layout_id(catalog[u])[:8],16)%8==0
                    counts['held_instances']+=n*held
                    if u>=len(original):
                        counts['added_instances']+=n
                        counts['distinct_added']+=1
                        counts['held_added_instances']+=n*held
                groups[kind]=counts
            ops=sum(run['ept']['signed_external']+run['ept']['signed_internal'])
            arms[tag]=dict(policy=report['policy'],paid=run['issued'],accepted=run['counts']['accepted'],
                           ops=ops,ept=ops/run['issued'],reference=report['reference_commits'],
                           residual=run['assist']['residual_commits'],groups=groups)
        reports[name]=dict(reachability=reachable,live=arms)
    return reports


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('root','donor','experiment','base','gold','out'):
        p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',required=True)
    a=p.parse_args()
    a.out.write_text(json.dumps(audit(a.root,read(a.donor/'program.json'),a.experiment,
                                      a.base,a.gold,a.cases),indent=2)+'\n')
