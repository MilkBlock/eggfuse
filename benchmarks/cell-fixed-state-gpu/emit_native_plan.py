"""Bake fixture-bound slot operands and affine matrices into a native input plan."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
import run as base
from dataset import canonical
p=argparse.ArgumentParser()
for key in ('corpus','slots','inputs','model','output'):p.add_argument('--'+key,type=Path,required=True)
a=p.parse_args();corpus=json.loads(a.corpus.read_text());slots={r['id']:r for r in json.loads(a.slots.read_text())['cases']};sources={r['id']:r for r in json.loads(a.inputs.read_text())['cases']};model=dict(np.load(a.model))
base.D=int(model['dimension']);base.POOL_OPS=bool(model['pool_ops']);base.OP=model['op'];base.EDGE=model['edge'];base.LITERAL=model['literal']
plans={};cases=[]
for r in corpus['records']:
    if r['split']!='test':continue
    c=slots[r['id']];entry,mapping=canonical(c)
    if entry!=r['entry'] or c['source_sha256']!=r['source_sha256']:raise ValueError('input identity mismatch')
    key=base.digest(base.structure(entry));plan=base.Plan(entry)
    plans.setdefault(key,dict(weight=plan.weight.tolist(),bias=plan.bias.tolist(),metadata=plan.metadata.tolist()))
    fields={}
    for row in c['rows']:
        ni=mapping[row['values'][-1]['eq']]
        fact=[row['table'],[['eq',v['sort'],mapping[v['eq']]] if 'eq' in v else ['literal',v['sort'],v['value']] for v in row['values'][:-1]]]
        fi=entry[ni].index(fact)
        for field in row['scalar_fields']:
            if 'slot' not in field['source']:raise ValueError('fixture expects slots')
            fields[ni,fi,field['column']]=dict(cell=field['cell'],template=field['template'],slot=field['source']['slot'])
    cases.append(dict(id=r['id'],source=sources[r['id']]['source'],source_sha256=c['source_sha256'],plan=key,reads=[fields[pos] for pos in plan.reads]))
result=dict(schema='cell-affine-initial-projection/v1',scope='initial-instance fixture addresses; no cross-stage relocation support',
    model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),plans=plans,cases=cases)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,separators=(',',':')))
print('plans',len(plans),'cases',len(cases))
