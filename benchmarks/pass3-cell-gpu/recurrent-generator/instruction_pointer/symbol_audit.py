"""Measure hash exposure and counterfactual user-symbol renames on a frozen Actor."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random

import torch

from catalog import Catalog, symbol
from rule_read import load_actor


def read(path):
    return json.loads(path.read_bytes())


def key(x):
    return json.dumps(x,sort_keys=True,separators=(',',':'))


class SymbolAudit(Catalog):
    def __init__(self, program):
        self.labels=set()
        super().__init__(program)

    def node(self,label):
        self.labels.add(key(label))
        return super().node(label)


def renamed_program(program,seed):
    """Rename opaque table/sort identifiers consistently in the compiler model view."""
    recipe=program['recipe']
    tables={t['name'] for t in recipe['tables']}
    sorts={s['name'] for t in recipe['tables'] for s in t['schema'] if s['kind']=='eq'}
    sorts.update(s['sort']['name'] for r in recipe['rules'] for s in r['slots'] if s['sort']['kind']=='eq')
    def aliases(domain,tag):
        ordered=sorted(domain)
        rng=random.Random(f'{seed}-{tag}')
        rng.shuffle(ordered)
        return {name:f'@renamed-{tag}-{i}' for i,name in enumerate(ordered)}
    tmap,smap=aliases(tables,'table'),aliases(sorts,'sort')

    def rewrite(obj):
        if isinstance(obj,list):
            return [rewrite(v) for v in obj]
        if not isinstance(obj,dict):
            return obj
        out={k:rewrite(v) for k,v in obj.items()}
        if 'table' in obj and isinstance(obj['table'],str):
            out['table']=tmap[obj['table']]
        if 'schema' in obj and obj.get('name') in tmap:
            out['name']=tmap[obj['name']]
        if obj.get('kind')=='eq' and obj.get('name') in smap:
            out['name']=smap[obj['name']]
        if 'primitive' in obj:
            out['inputs']=[smap.get(s,s) for s in obj['inputs']]
            out['output']=smap.get(obj['output'],obj['output'])
        return out
    return rewrite(program)


def audit(root,weights):
    torch.set_num_threads(1)
    model=load_actor(weights,True)
    all_labels=defaultdict(set)
    cache={}
    rows=read(root/'manifest.json')
    for record in rows:
        path=root/record['directory']/'program.json'
        raw=path.read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
        if digest not in cache:
            cache[digest]=SymbolAudit(json.loads(raw)).labels
        all_labels[record['split']].update(cache[digest])
    def buckets(labels):
        return {symbol(json.loads(label)) for label in labels}
    training=all_labels['train']
    exposed=buckets(training)
    # Graph-only counterfactual. Runtime rows, rules, version filters and token
    # addresses retain the same indices. Only compiler-visible names change.
    perturbations={}
    from semantic_catalog import SemanticActor,SemanticCatalog
    torch.manual_seed(1703)
    probes=['loopfact']+[next(r['directory'] for r in rows if r['split']==s and r['collision'])
                         for s in ('held_program','held_merge','held_result_pc')]
    with torch.no_grad():
        for name in probes:
            pg=read(root/name/'program.json')
            renamed=renamed_program(pg,1703)
            before,after=Catalog(pg),Catalog(renamed)
            a,b=model.template_graph(before),model.template_graph(after)
            u,v=SemanticCatalog(pg),SemanticCatalog(renamed)
            if (u.factors!=v.factors or u.constants!=v.constants or u.edges!=v.edges or
                u.outputs!=v.outputs or u.atoms!=v.atoms or u.field_links!=v.field_links or
                u.seminaive!=v.seminaive):
                raise ValueError('typed structure changed under alpha renaming')
            typed=SemanticActor(sorted({x for row in u.factors for x in row}))
            if not torch.equal(typed.template_graph(u),typed.template_graph(v)):
                raise ValueError('structural node states depend on user spelling')
            perturbations[name]=dict(original_nodes=len(a),old_changed=int((a!=b).any(1).sum()),
                                     structural_nodes=len(u.nodes),structural_changed=0)
    report={}
    for split,labels in all_labels.items():
        occupied=buckets(labels)
        report[split]=dict(labels=len(labels),occupied=len(occupied),
            unseen_labels=len(labels-training),unexposed_buckets=len(occupied-exposed),
            unseen_labels_in_occupied_buckets=sum(symbol(json.loads(s)) in exposed for s in labels-training),
            excess_labels_due_to_collisions=len(labels)-len(occupied))
    return dict(mode='catalog-only',weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),
        checkpoint_parameters=sum(p.numel() for p in model.parameters()),static_parameters=model.static.weight.numel(),
        static_shape=list(model.static.weight.shape),catalogs=len(rows),compiled_bytes_distinct=len(cache),
        training_random_merge_families=len({r['merge_family'] for r in rows if r['split']=='train' and 'merge_family' in r}),
        exposure=report,paired_rename=perturbations)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('root','weights','output'):
        p.add_argument(k,type=Path)
    a=p.parse_args()
    a.output.write_text(json.dumps(audit(a.root,a.weights),indent=2)+'\n')
