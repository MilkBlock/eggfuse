"""Freeze the trained graph encodings and independent input roles once per library."""
import argparse
import json
from pathlib import Path

import torch

from anchor_set_audit import load_actor
from alternate_proofs import digest
from higher_cell import read
from ripsat_layout import signatures
from ripsat_boundary import slots
from ripsat_policy import CellScorer,compile_graphs
from ripsat_replay import unpack


@torch.no_grad()
def bake(donor,weights,folder):
    study=read(folder/'study.json')
    if digest(weights)!=study['root_weights'] or digest(folder/'catalog.json')!=study['catalog_sha'] or digest(folder/'shared.pt')!=study['weights']:
        raise ValueError('frozen graph inputs changed')
    layouts=unpack(read(folder/'catalog.json'))
    actor=load_actor(weights,True)
    cat=actor.catalog_type(donor)
    nodes=actor.template_graph(cat)
    model=CellScorer(actor.width).eval()
    model.load_state_dict(torch.load(folder/'shared.pt',weights_only=True))
    codes=model.encode(compile_graphs(layouts,cat,nodes))
    unique={}
    inputs=[]
    for layout in layouts:
        roles=[]
        for t,uses in slots(layout,donor['recipe']['rules']):
            source=tuple(cat.inputs['generated',rid][role] for _,rid,role in uses)
            roles.append((t,unique.setdefault(source,len(unique))))
        inputs.append(roles)
    role_codes=torch.stack([nodes[list(source)].mean(0) for source in unique])
    torch.save(dict(codes=codes,roles=role_codes),folder/'codes.pt')
    spec=dict(catalog=study['catalog_sha'],scorer=study['weights'],root_weights=study['root_weights'],
              codes=digest(folder/'codes.pt'),signatures=signatures(donor),inputs=inputs)
    (folder/'fixed.json').write_text(json.dumps(spec,separators=(',',':'))+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('donor','weights','folder'):
        p.add_argument(k,type=Path)
    a=p.parse_args()
    torch.set_num_threads(1)
    bake(read(a.donor/'program.json'),a.weights,a.folder)
