"""Compile finite constructor congruence implications from a pre-union graph."""
import argparse
import hashlib
from itertools import combinations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE.parent / 'eclass_ablation/corpus/manifest.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_instance(template, initial, declarations):
    sorts = {table['name']: table for table in declarations}
    vertices = {}
    def intern(value):
        key = (value['sort'],value['eq'])
        return vertices.setdefault(key,len(vertices))

    constructors = {}
    observed = {}
    for row in initial['rows']:
        if row['subsumed']:
            continue
        values = row['values']
        if row['table']=='Observe':
            observed[values[0]['value']] = intern(values[1])
        spec = sorts[row['table']]
        if spec['kind']!='constructor' or 'eq' not in values[-1]:
            continue
        terms = tuple(('node',intern(v)) if 'eq' in v else
                      ('literal',v['sort'],v['value']) for v in values[:-1])
        constructors.setdefault(row['table'],[]).append((terms,intern(values[-1])))

    implications = []
    for name, applications in constructors.items():
        for (left,out_a),(right,out_b) in combinations(applications,2):
            if out_a==out_b:
                continue
            guards=[]
            for a,b in zip(left,right,strict=True):
                if a==b:
                    continue
                if a[0]!='node' or b[0]!='node':
                    break
                guards.append([a[1],b[1]])
            else:
                if not guards:
                    raise ValueError('unrepaired input constructor table')
                implications.append(dict(table=name,requires=guards,unifies=[out_a,out_b]))
    ports=template['public_ports']
    public=[[observed[16*owner+port] for port in ports] for owner in (0,1)]
    certificate,=template['certificates']
    pair=[ports.index(certificate[k]) for k in ('left_port','right_port')]
    if len(set(public[0]+public[1]))!=6:
        raise ValueError('expected six distinct initial public endpoints')
    return dict(vertices=len(vertices),ports=ports,public=public,local_pair=pair,implications=implications)


def main(raw,out):
    records={row['id']:row for row in json.loads(raw.read_text())['cases']}
    templates=json.loads(MANIFEST.read_text())['templates']
    compiled={}
    for t in templates:
        r=records['r'+t['id'].split('-')[-1]+'-enabled']
        if t['source'] not in r['source']:
            raise ValueError('template and witness belong to different rules')
        compiled[t['id']]=compile_instance(t,r['initial'],r['compiled_program']['recipe']['tables'])
    result=dict(schema='eggfuse.initial-constructor-plan/v1',initial_archive_sha256=digest(raw),
                templates_sha256=digest(MANIFEST),plans=compiled)
    out.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('raw',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    main(args.raw,args.output)
