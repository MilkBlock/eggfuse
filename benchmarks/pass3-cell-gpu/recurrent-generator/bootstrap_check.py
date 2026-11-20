"""Replay restricted inference and locate the first source obligation it cannot generate."""
import argparse
import json
import tempfile
from pathlib import Path

import numpy as np

from capture import inputs, load_catalog, read, verify
from isolate import sha
from online import run
from provenance import validate


def compare(dest, gold, entries, rules, residual):
    credited = validate(dest,entries)
    with np.load(dest/'output.npz') as observed, np.load(gold/'output.npz') as reference:
        with np.load(dest/'neural-output.npz') as neural:
            exact = np.ones(len(observed['rhs']), dtype=bool)
            ordinal = neural['rhs_ordinal']
            exact[ordinal[ordinal>0]-1] = False
        exact_rules = observed['rhs'][exact,1]
        assert len(exact_rules)+credited==len(observed['rhs'])
        if residual!='full':
            assert all(not rules[r]['query'] for r in exact_rules)
        if residual=='none':
            assert not len(exact_rules)
        first = None
        for index, (now,old) in enumerate(zip(observed['runs'],reference['runs']),1):
            if not np.array_equal(now,old):
                first = index
                break
            for k in ('rhs','writes','resumes'):
                a = observed[k][observed[k][:,0]==index]
                b = reference[k][reference[k][:,0]==index]
                if k=='rhs':
                    a,b = a[:,[0,1,*range(4,a.shape[1])]],b[:,[0,1,*range(4,b.shape[1])]]
                if not np.array_equal(a,b):first=index;break
            if first:break
        if first is None and len(observed['runs']) != len(reference['runs']):
            first=min(len(observed['runs']),len(reference['runs']))+1
        missing=[]
        if first is not None:
            def bindings(z):
                from collections import Counter
                return Counter(tuple(map(int,r[1:2]))+tuple(map(int,r[4:])) for r in z['rhs'] if r[0]==first)
            for token,n in (bindings(reference)-bindings(observed)).items():
                rid=token[0];missing.append(dict(rule=rid, multiplicity=n, atoms=len(rules[rid]['query']),
                                                  in_leaf_catalog=any(e[0]==rid for e in entries)))
        return dict(source_runs=len(reference['runs']),actual_runs=len(observed['runs']),source_rhs=len(reference['rhs']),
                    exact_rhs=len(exact_rules),exact_rule_ids=sorted(set(map(int,exact_rules))),neural_rhs=credited,
                    matched_prefix_runs=first-1 if first else len(reference['runs']),first_divergence=first,
                    missing_at_divergence=missing)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','capture','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for n in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        image,program,gold=inputs(a.corpus,a.ref,n)
        entries=load_catalog(image,program,a.ref/'sum-bits/program.json')
        rules=read(program)['recipe']['rules']
        with tempfile.TemporaryDirectory() as tmp:
            catalog=Path(tmp)/'catalog.json'
            catalog.write_text(json.dumps(dict(schema='eggfuse.leaf-catalog/v1',entries=entries,image_sha256=sha(image/'device.json'))))
            for seed in (1703,1709):
                for residual in ('none','empty-lhs','full'):
                    dest=a.out/f'{n}-{seed}-{residual}'
                    run(image/'device.json',a.reader,a.ref/'ports-1703.pt',catalog,a.capture/f'train-{seed}-2/actor.json',
                        dest,residual=='full',residual=='empty-lhs')
                    if residual=='full':verify(dest,gold,image)
                    stats=compare(dest,gold,entries,rules,residual)
                    assert (stats['first_divergence'] is None)==(residual=='full')
                    report[f'{n}/{seed}/{residual}']=stats
                    (a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
                    print(n,seed,residual,stats['matched_prefix_runs'],stats['neural_rhs'],flush=True)
