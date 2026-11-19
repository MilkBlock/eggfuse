"""Compare exported checks and projections with direct evaluation of raw Bake entries."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random

from export import HERE, ROOT, digest, family, require


def read_operand(operand, a, b):
    side, column = operand
    if side == 2:
        return column
    return (a,b)[side][column]


def execute(stage, a, b):
    if any(read_operand(x,a,b) != read_operand(y,a,b) for x,y in stage['checks']):
        return None
    return tuple(read_operand(route,a,b) for route in stage['outputs'])


def source_make(rule, output, a, b):
    effect = rule['effects'][output]
    operands = effect['args'] + ([effect['value']] if effect['op'] == 'set' else [])
    slots = list(dict.fromkeys(op['slot'] for op in operands if 'slot' in op))
    frame = dict(zip(slots,a))
    args = tuple(op['literal'] if 'literal' in op else frame[op['slot']] for op in operands)
    if args != tuple(b[:len(operands)]):
        return None
    return tuple(b)


def source_finish(rule, entry, anchor, request):
    args=rule['query'][entry['pivot']]['args']
    slots = {}
    for op, value in zip(args, anchor):
        if 'literal' in op:
            if op['literal'] != value: return None
        elif slots.setdefault(op['slot'],value) != value:
            return None
    block=entry['block']; port=block['port']; width=len(block['inputs'])
    def read(ref):
        if ref == 'PortResult':return request[-1]
        if 'Anchor' in ref:return anchor[ref['Anchor']]
        return next(iter(ref['Literal'].values()))
    if port is not None:
        if tuple(request[width:-1])!=tuple(map(read,port['key'])):return None
        if port['check_result'] is not None and request[-1]!=read(port['check_result']):return None
    projected=tuple(map(read,block['inputs']))
    return projected if projected == tuple(request[:width]) else None


def active_instance(stages,rng):
    # Solve only the synthetic test constraints offline, including catalog literals.
    # This witness is used to exercise positive branches and single-column mutants.
    parent={};groups={}
    def root(x):
        if x not in parent:parent[x]=x
        if x!=parent[x]:parent[x]=root(parent[x])
        return parent[x]
    def union(x,y):parent[root(x)]=root(y)
    def address(n,operand):
        side,col=operand
        if side==2:return ('literal',col)
        if n==1 and side==0:return address(0,stages[0]['outputs'][col])
        return (n,side,col)
    for n,stage in enumerate(stages):
        for side,types in enumerate((stage['left_sorts'],stage['right_sorts'])):
            for j,sort in enumerate(types):
                ref=address(n,[side,j]);root(ref)
                if sort=='Unit':union(ref,('literal',0))
        for x,y in stage['checks']:union(address(n,x),address(n,y))
    for ref in parent:
        if ref[0]=='literal':
            group=root(ref);require(groups.setdefault(group,ref[1])==ref[1],'unsatisfiable static literals')
    for ref in parent:groups.setdefault(root(ref),rng.randrange(8))
    def side(n,index):return [groups[root(address(n,[index,col]))] for col in range(stages[n][('left_width','right_width')[index]])]
    return side(0,0),side(0,1),side(1,1)


def verify_templates(manifest,programs):
    rng=random.Random(320193);stats=Counter();held={t['family_id'] for t in manifest['templates'] if t['split']=='heldout'}
    for t in manifest['templates']:
        g=t['graph'];n=len(g['nodes']);perm=list(range(n));rng.shuffle(perm);renamed=[None]*n
        for index,node in enumerate(g['nodes']): renamed[perm[index]]={**node,'ordinal':101-index,'sort':'renamed'}
        equivalent=dict(nodes=renamed,edges=[[perm[u],k,perm[v]] for u,k,v in reversed(g['edges'])],readouts=[[perm[i] for i in ports] for ports in g['readouts']]);require(family(equivalent)==t['family_id'],'renumbered/retagged graph escaped family grouping')
        for p in t['provenance']:
            program=programs[p['catalog']];rules=program['recipe']['rules'];entries=program['spine_blocks']['entries']
            left,right=entries[p['left']],entries[p['right']]
            require(rules[left['consumer']]['metadata']['name']==p['source_rule_text'],'wrong producer lineage')
            require(rules[right['consumer']]['metadata']['name']==p['consumer_rule_text'],'wrong consumer lineage')
            stats['original_two_leaf_joins']+=1
            for _ in range(16):
                a,b,r=active_instance(t['stages'],rng)
                def run(a,b,r):
                    first=execute(t['stages'][0],a,b)
                    first_ref=source_make(rules[p['source_rule']],p['output_operation'],a,b)
                    require(first==first_ref,'make semantics differ');stats['make_comparisons']+=1
                    if first is None:return None
                    second=execute(t['stages'][1],first,r)
                    second_ref=source_finish(rules[p['consumer_rule']],right,first,r)
                    require(second==second_ref,'finish semantics differ');stats['finish_comparisons']+=1
                    return second
                require(run(a,b,r) is not None,'generated witness rejected');stats['positive_two_stage']+=1
                for side,values in enumerate((a,b,r)):
                    for col in range(len(values)):
                        inputs=[list(a),list(b),list(r)];inputs[side][col]=(values[col]+1)%8
                        result=run(*inputs);stats['rejected_column_mutants' if result is None else 'admitted_column_mutants']+=1
    train={t['family_id'] for t in manifest['templates'] if t['split']=='train'}
    require(not held&train,'train/heldout overlap')
    require(all(len(p['lineage']) == 1 for t in manifest['templates'] for p in t['provenance']),'composite descendants in sample')
    return dict(stats)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('sum_bits_program',type=Path);parser.add_argument('raytrace_program',type=Path)
    args=parser.parse_args();manifest=json.loads((HERE/'manifest.json').read_text());programs={k:json.loads(p.read_text()) for k,p in [('sum-bits',args.sum_bits_program),('raytrace',args.raytrace_program)]}
    checks=verify_templates(manifest,programs)
    report=dict(status='pass',manifest_sha256=digest(manifest),checks=checks)
    (HERE/'validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
