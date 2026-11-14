"""Audit real compiled ruleset membership and nested stage control, without training."""
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
from device_stage_models import membership
from device_schedule import compile_schedule,RUN


def audit(recipe):
    names,matrix,authoritative=membership(recipe)
    if not authoritative:raise ValueError('full compiler ruleset membership required')
    plan,meta=compile_schedule(recipe['control'],names)
    uses=Counter(int(i) for i in plan['stage'][plan['op']==RUN])
    modules=[]
    for i,name in enumerate(names):
        ids=np.flatnonzero(matrix[:,i]).tolist();rules=[recipe['rules'][r] for r in ids]
        shapes=Counter((len(r['query']),max((len(a['args']) for a in r['query']),default=0),len(r['slots'])) for r in rules)
        modules.append(dict(name=name,rule_ids=ids,run_sites=uses[i],source_annotations=dict(Counter(r.get('metadata',{}).get('source_set') for r in rules)),shape_groups=[dict(query_atoms=k[0],query_fields=k[1],slots=k[2],rules=v) for k,v in sorted(shapes.items())]))
    return dict(scope='Compiler schedule/membership audit only; not trained stage models or full GPU execution',rules=len(recipe['rules']),rulesets=len(names),scheduled_rulesets=len(uses),run_sites=sum(uses.values()),schedule_instructions=meta['instructions'],saturation_scopes=meta['saturation_slots'],repeat_scopes=meta['repeat_slots'],multi_ruleset_rules=int((matrix.sum(axis=1)>1).sum()),rules_outside_all_rulesets=int((matrix.sum(axis=1)==0).sum()),ruleset_membership_authoritative=True,modules=modules)


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    src=json.loads(a.trace.read_text());recipe=src.get('recipe',src)
    report=audit(recipe);report['recipe_sha256']=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='modules'}))


if __name__=='__main__':main()
