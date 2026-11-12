"""Read-only real recipe census; reports static opportunities, not executions."""
import argparse,collections,hashlib,json
from pathlib import Path
from compiler import Affine,Unsupported
p=argparse.ArgumentParser();p.add_argument('--program',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
data=json.loads(a.program.read_text());rows=[];ops=collections.Counter();failures=collections.Counter();bound=1<<20
for i,r in enumerate(data['recipe']['rules']):
 computes=[o for o in r['effects'] if o.get('kind')=='compute'];ops.update(o['call']['primitive'] for o in computes)
 inputs=[s for s,v in enumerate(r['slots']) if v['definition']=='query' and v['sort']['kind']=='i64']
 row=dict(rule=i,primitive_count=len(computes),query_primitive_count=sum('primitive' in x['call'] for x in r['query']))
 if not computes:rows.append(row);continue
 try:
  plan=Affine(r,inputs,[bound]*len(inputs))
  row.update(certified=True,scalar_destinations=len(plan.all_destinations),unique_columns=len(plan.destinations),output_columns=plan.output_columns)
 except Unsupported as e:row.update(certified=False,reason=str(e));failures[str(e)]+=1
 rows.append(row)
result=dict(scope='Static saved recipe census, not dynamic execution or speedup',program_sha256=data['sha256'],file_sha256=hashlib.sha256(a.program.read_bytes()).hexdigest(),
 rules=len(rows),rules_with_rhs_primitives=sum(r['primitive_count']>0 for r in rows),max_rhs_primitives=max(r['primitive_count'] for r in rows),max_query_primitives=max(r['query_primitive_count'] for r in rows),
 certified_rules=sum(r.get('certified',False) for r in rows),duplicate_columns_removed=sum(r.get('scalar_destinations',0)-r.get('unique_columns',0) for r in rows),primitive_histogram=dict(ops),rejections=dict(failures),input_bound=bound,rows=rows)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
