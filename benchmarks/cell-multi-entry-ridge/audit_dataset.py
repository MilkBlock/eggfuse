"""Independent label-renaming and containment-negative audit of dataset canonicalizer."""
import argparse,copy,hashlib,importlib.util,json,random
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 path=Path(__file__).parent/'dataset.py';spec=importlib.util.spec_from_file_location('candidate_dataset',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 raw=json.loads(a.runtime.read_text());rng=random.Random(37);checks=0
 for case in raw['cases']:
  for field in ('initial','final','native_final'):
   original=case[field];expected,_=m.canonical(original);changed=copy.deepcopy(original)
   ids={v['eq']for row in changed['rows']for v in row['values'] if 'eq'in v};labels=list(ids);rng.shuffle(labels);rename={old:f'audit-{i}'for i,old in enumerate(labels)}
   for row in changed['rows']:
    for v in row['values']:
     if 'eq'in v:v['eq']=rename[v['eq']]
   rng.shuffle(changed['rows']);got,_=m.canonical(changed)
   assert got==expected,(case['id'],field);checks+=1
 # A fact superset cannot establish sufficiency: add an unrelated fresh Input.
 case=raw['cases'][0];actual,_=m.canonical(case['final']);superset=copy.deepcopy(case['final'])
 superset['rows'].append(dict(table='Input',values=[dict(sort='i64',value=9223372036854775000),dict(sort='Expr',eq='audit-extra-output')],subsumed=False))
 wrong,_=m.canonical(superset);assert wrong!=actual
 # At original identifiers every old final fact (and projected entry) survives.
 assert all(row in superset['rows'] for row in case['final']['rows'])
 result=dict(canonical_renaming_checks=checks,cases=len(raw['cases']),containment_negative=dict(old_facts_retained=True,exact_completion_equal=False,reason='unjustified extra Input fact'),native_cases_with_anchors=sum(bool(c['native_final']['anchors'])for c in raw['cases']),dataset_source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),runtime_sha256=hashlib.sha256(a.runtime.read_bytes()).hexdigest())
 a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
