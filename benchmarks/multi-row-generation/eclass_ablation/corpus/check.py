"""Check family isolation, replay coverage and the previous catalog's proof census."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import random

from export import HERE, group_key, require


def main():
    parser=argparse.ArgumentParser();parser.add_argument('sum_program',type=Path);parser.add_argument('ray_program',type=Path)
    args=parser.parse_args();programs={name:json.loads(p.read_text()) for name,p in [('sum-bits',args.sum_program),('raytrace',args.ray_program)]}
    manifest=json.loads((HERE/'manifest.json').read_text());events=json.loads((HERE/'extra-events.json').read_text());replays=json.loads((HERE/'replay-evidence.json').read_text())
    templates=manifest['templates'];partitions={t['split']:{u['family_id'] for u in templates if u['split']==t['split']} for t in templates}
    require(not partitions['heldout']&partitions['train'], 'family leakage')
    rng=random.Random(230413);permutation_checks=0
    for t in templates:
        graph=t['graph'];n=len(graph['nodes']);perm=list(range(n));rng.shuffle(perm);nodes=[None]*n
        for i,node in enumerate(graph['nodes']):nodes[perm[i]]={**node,'sort':'other','ordinal':1000-i}
        edges=[[perm[u],rel,perm[v]] for u,rel,v in reversed(graph['edges'])]
        require(group_key({'nodes':nodes,'edges':edges})==t['family_id'],'renamed graph changed class');permutation_checks+=1
    baked=json.loads((HERE.parents[1]/'port_ablation/corpus/manifest.json').read_text());census=Counter();ids=[]
    for t in baked['templates']:
        categories=set()
        for prov in t['provenance']:
            r=programs[prov['catalog']]['recipe']['rules'][prov['source_rule']];ops=r['effects']
            union_slots={arg['slot'] for e in ops if e['kind']=='union' for arg in e['args'] if 'slot' in arg}
            effect=ops[prov['output_operation']];operands=effect.get('args',[])+([effect['value']] if 'value' in effect else [])
            selected={a['slot'] for a in operands if 'slot' in a}|({effect['dst']} if 'dst' in effect else set())
            categories.add('published_column_is_union_endpoint' if selected&union_slots else 'producer_union_other_slots' if union_slots else 'no_explicit_producer_union')
        require(len(categories)==1, 'cross-workload certificate mismatch');kind,=categories;census[kind]+=1;ids.append(dict(template=t['id'],category=kind))
    external=[c for c in events['cases'] if c['external_endpoints'] is not None];secondary=[c['id'] for c in external if c['secondary_congruence']]
    require(len(external)==9*len(templates) and len(events['cases'])==10*len(templates),'missing replay category')
    result=dict(status='pass',template_count=len(templates),family_counts={k:len(v) for k,v in partitions.items()},
                templates_per_split=dict(Counter(t['split'] for t in templates)),old_catalog_census=dict(census),old_catalog_templates=ids,
                verified_node_permutations=permutation_checks,base_replays=len(replays),dynamic_replays=len(events['cases']),
                raw_external_cases=len(external),with_secondary_congruence=secondary,
                installed_local_union_cells={k:'local_union_cells' in p for k,p in programs.items()},
                files={f:sha256((HERE/f).read_bytes()).hexdigest() for f in ('manifest.json','replay-evidence.json','extra-events.json')})
    (HERE/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('old_catalog_templates','files')}))


if __name__=='__main__':main()
