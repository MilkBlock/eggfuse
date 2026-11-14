"""Paired inputs differing in one explicit initial Eq; no outcome-based selection."""
import argparse,json,random
from pathlib import Path
from itertools import combinations
from synthetic_cell_inputs import generate,merge_input,oracle,digest
from device_snapshot_import import identity


def pair(recipe,seed):
    base=generate(recipe,seed,4,0.)
    values={identity(v):v for row in base['rows'] for v in row['values'] if 'eq' in v}
    choices=[(a,b) for a,b in combinations(values.values(),2) if a['sort']==b['sort']]
    if not choices:raise ValueError('no same-sort pair')
    left,right=random.Random(seed).choice(choices)
    return base,merge_input(recipe,base,left,right),[left,right]


def main():
    p=argparse.ArgumentParser();p.add_argument('recipe',type=Path);p.add_argument('output',type=Path);p.add_argument('--seed',type=int,default=20261200);p.add_argument('--count',type=int,default=4);a=p.parse_args()
    if a.count<1:raise ValueError('positive count')
    recipe=json.loads(a.recipe.read_text());a.output.mkdir(parents=True,exist_ok=True);records=[]
    for seed in range(a.seed,a.seed+a.count):
        base,merged,edge=pair(recipe,seed)
        for variant,snapshot in [('base',base),('eq',merged)]:
            name=str(seed)+'-'+variant;g=dict(seed=seed,fragments=4,reuse=0.)
            if variant=='eq':g['initial_merge']=edge
            doc=dict(schema='synthetic-cell-input/v1',recipe=recipe,snapshot=snapshot,recipe_sha256=digest(recipe),input_sha256=digest(snapshot),generator=g,
                source='rule definitions only; paired initial Eq',reachability='rule-valid; source-program reachability unproved')
            (a.output/(name+'.json')).write_text(json.dumps(doc,indent=2)+'\n')
            rec=dict(case=name,pair=seed,variant=variant,input_sha256=doc['input_sha256'])
            try:
                label=oracle(recipe,snapshot);rec.update(status='complete',runs=len(label['runs']),unions=label['unions'])
                (a.output/(name+'.label.json')).write_text(json.dumps(label,indent=2)+'\n')
            except ValueError as e:rec.update(status='rejected',reason=str(e))
            records.append(rec)
    report=dict(scope='one initial Eq per pair, including mandatory constructor closure; not a one-row mutation',records=records)
    (a.output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
