"""Bake field positions shared by the external ports of a signed Cell graph."""
from collections import defaultdict
import json

import torch
from torch import nn

from alternate_proofs import digest
from higher_cell import read
from ripsat_layout import queries
from side_pointer import bits


def rule_fields(rule):
    # A copy reads an already defined slot. Effects can only use earlier values.
    alias = {}
    def origin(arg):
        slot = arg.get('slot')
        return alias.get(slot,slot)
    inputs = [tuple(origin(a) for a in atom['args']) for atom in queries(rule)]
    outputs = {}
    for pc,op in enumerate(rule['effects']):
        if op['op']=='copy':
            alias[op['dst']] = origin(op['arg'])
        elif op['op'] in ('let','set') and 'table' in op['call']:
            # Set may merge with an old mutable value. Only its keys are routed.
            result = origin({'slot':op['dst']}) if op['op']=='let' else None
            outputs[pc] = (*map(origin,op['args']),result)
    return inputs,outputs


def routes(layout, rules):
    parent = {}
    def find(key):
        while key in parent:
            target = parent[key]
            parent[key] = parent.get(target,target)
            key = target
        return key
    def link(a,b):
        a,b=find(a),find(b)
        if a!=b:
            parent[a]=b
    boundary = set()
    for step,(rid,_,wires) in enumerate(layout):
        for args,(owner,port) in zip(rules[rid][0],wires,strict=True):
            if owner<0:
                for col,var in enumerate(args):
                    field=(-1,port,col)
                    boundary.add(field)
                    if var is not None:
                        link(field,(step,var))
            else:
                returned=rules[layout[owner][0]][1][port]
                for src,dst in zip(returned,args,strict=True):
                    if src is not None and dst is not None:
                        link((owner,src),(step,dst))
    classes=defaultdict(list)
    for field in sorted(boundary):
        classes[find(field)].append(field[1:])
    n=1+max((slot for _,_,wires in layout for owner,slot in wires if owner<0),default=-1)
    result=[[] for _ in range(n)]
    for members in classes.values():
        for i,(slot,col) in enumerate(members):
            result[slot].extend((prev,src,col) for prev,src in members[:i] if prev<slot)
    return tuple(tuple(sorted(group)) for group in result)


def bake_routes(donor, layouts, out):
    rules=[rule_fields(r) for r in donor['recipe']['rules']]
    bank={}
    uses=[]
    for layout in layouts:
        uses.append([bank.setdefault(links,len(bank)) for links in routes(layout,rules)])
    path=out/'routes.json'
    path.write_text(json.dumps(dict(uses=uses,bank=list(bank)),separators=(',',':'))+'\n')
    return RouteBank(read(path))


class RouteBank:
    def __init__(self, spec):
        self.bank=spec['bank']
        self.uses=spec['uses']

    def has_links(self,uid,slot):
        return bool(self.bank[self.uses[uid][slot]])

    def features(self, uid, slot, known, rows):
        links=self.bank[self.uses[uid][slot]]
        if not links:
            return torch.zeros(len(rows),3)
        source=[known[p][i] for p,i,_ in links]
        cols=[j for _,_,j in links]
        keys=bits(rows,len(rows[0]))[:,cols]
        scores=(keys*bits([source],len(source))).mean(-1)
        return torch.stack((scores.amin(1),scores.mean(1),scores.amax(1)),1)


class FieldReader:
    def __init__(self, folder, baked):
        meta=read(folder/'training.json')
        if (any(meta[k]!=digest(baked/k) for k in ('codes.pt','boundary.pt','catalog.json','fixed.json'))
                or meta['routes']!=digest(folder/'routes.json') or meta['weights']!=digest(folder/'field.pt')):
            raise ValueError('field readout differs from its trained graph library')
        self.checkpoint=digest(folder/'training.json')
        self.routes=RouteBank(read(folder/'routes.json'))
        self.model=nn.Linear(3,1,bias=False).eval()
        self.model.load_state_dict(torch.load(folder/'field.pt',weights_only=True))

    def adjustment(self,uid,slot,known,rows):
        return self.model(self.routes.features(uid,slot,known,rows)).flatten()
