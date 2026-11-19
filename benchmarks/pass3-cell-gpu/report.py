"""Collect input and completed schedule evidence without treating a partial run as acceptance."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
from audit import canonical,graph,typed


def read(p):return json.loads(p.read_text())


def report(root):
    result={};initial=[]
    for name in ('sum-bits','dot-product'):
        program=root/name/'program.json';packet=root/f'input-{name}'/'ingress.json'
        baseline=root/f'oracle-{name}';p=read(packet);raw=read(program)
        initial.append(raw['initial'])
        out=dict(program_sha256=p['program_sha256'],source_sha256=read(root/name/'manifest.json')['files']['source.egg'],
                 ingress=read(root/f'input-{name}'/'reader-audit.json'),input_matrix={},rows={})
        for form in ('input','single'):
            shape=read(root/f'{form}-{name}'/'ingress.json')
            for reader in ('learned','exact'):
                d=(root/f'prefix-{name}-2' if (form,reader)==('input','learned')
                   else root/f'ingress-{name}-{form}-{reader}')
                audit=read(d/'check.json')
                stages=audit['runs'][:3]
                ok=all(s['graph'] and s['rhs'] and s['writes'] and s['schedule'] and s['spine_empty_ref'] for s in stages)
                if not (audit['initial_exact'] and ok and len(stages)==3):raise ValueError((name,form,reader))
                out['input_matrix'][form+'/'+reader]=dict(instances=len(shape['instances']),templates=len(shape['templates']),
                    fully_checked_runs=len(stages),first_run_facts=stages[0]['facts'])
        one=None
        for lanes in (1,2):
            d=root/f'final-{name}-{lanes}';run=read(d/'run.json');res=read(d/'check.json')
            ref=read(baseline/'state.json')
            with np.load(d/'output.npz',allow_pickle=False) as z:
                eq,ok=graph(z['rows'],z['meta'],ref,p,run['strings'],z['parents'])
                got=[]
                for row,m in zip(z['rows'],z['meta']):
                    if m[3]==2:continue
                    t=p['tables'][m[0]]
                    got.append(canonical(dict(table=t['name'],subsumed=bool(m[3]),
                        values=[typed(s,v,eq,run['strings']) for s,v in zip(t['schema'],row)])))
                want=Counter(map(canonical,ref['rows']));actual=Counter(got)
                res['extra_by_table']=dict(Counter(read_table(x) for x in (actual-want).elements()))
                res['missing_by_table']=dict(Counter(read_table(x) for x in (want-actual).elements()))
                assert ok==res['full_typed_graph_equal']
                # Project out lane and pivot; compare all actual ordered rule inputs.
                signature=hashlib.sha256()
                for row in z['rhs']:
                    signature.update(row[:2].tobytes());signature.update(row[4:4+len(p['rules'][int(row[1])]['inputs'])].tobytes())
                device_outputs=(signature.hexdigest(),hashlib.sha256(z['writes'].tobytes()).hexdigest(),actual)
                if lanes==1:one=device_outputs
                else:
                    res['same_as_one_row']=(device_outputs==one)
                    if not res['same_as_one_row']:raise ValueError('row decomposition changed device results')
            out['rows'][str(lanes)]=res
        prefix=read(root/f'prefix-{name}-2'/'check.json')['runs']
        out['prefix']=prefix
        init,=next(s['rule_ids'] for s in raw['recipe']['rulesets'] if s['name']=='initialization')
        out['initialization_effects']=dict(Counter(e['kind'] for e in raw['recipe']['rules'][init]['effects']))
        result[name]=out
    return dict(shared_initial=initial[0]==initial[1],scope='GPU ingress and experimental Pass 3; full acceptance incomplete',cases=result)


def read_table(s):return json.loads(s)['table']


if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('root',type=Path);cli.add_argument('out',type=Path)
    a=cli.parse_args();r=report(a.root);a.out.parent.mkdir(exist_ok=True)
    a.out.write_text(json.dumps(r,ensure_ascii=False,indent=1)+'\n')
