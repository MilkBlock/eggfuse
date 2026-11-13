"""Join held-out recurrent audits to training coverage; never mutate training."""
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
from corpus_cell_ridge import load_records


def category(row):
    if row['exact_target'] and row['stopped']:return 'success'
    if row['initially_novel'] and not any(row['emissions']):return 'missed_initial_emission'
    if not row['stopped']:return 'still_active'
    return 'wrong_target_stopped'


def joined(left,right,manifest_hash):
    if left['manifest_sha256']!=manifest_hash or right['manifest_sha256']!=manifest_hash:raise ValueError('manifest mismatch')
    if left['rounds']!=right['rounds']:raise ValueError('different rollout lengths')
    if not left['numerical_audit']['passed'] or not right['numerical_audit']['passed']:raise ValueError('failed numerical audit')
    a={r['identity']:r for r in left['cases']};b={r['identity']:r for r in right['cases']}
    if len(a)!=len(left['cases']) or len(b)!=len(right['cases']):raise ValueError('duplicate case identity')
    if a.keys()!=b.keys():raise ValueError('case coverage mismatch')
    return [(a[k],b[k]) for k in sorted(a)]


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('left',type=Path);p.add_argument('right',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    mh=hashlib.sha256(a.manifest.read_bytes()).hexdigest();left=json.loads(a.left.read_text());right=json.loads(a.right.read_text());pairs=joined(left,right,mh)
    records,_=load_records(json.loads(a.manifest.read_text()));training={r['identity']:r for r in records if r['split']=='train'};test={r['identity']:r for r in records if r['split']=='test'};families=Counter(r['family'] for r in training.values())
    if {l['identity'] for l,_ in pairs}!=test.keys():raise ValueError('audit does not cover test partition')
    rows=[];cross=Counter();coverage=Counter();all_coverage=Counter();outcomes=Counter()
    for l,r in pairs:
        rec=test[l['identity']];s=rec['sample'];lc,rc=category(l),category(r)
        if l['family']!=rec['family'] or r['family']!=rec['family']:raise ValueError('family mismatch')
        cov='exact_training_input' if rec['identity'] in training else 'new_input_known_family' if families[rec['family']] else 'uncovered_family'
        all_coverage[cov]+=1;outcomes[(lc,rc)]+=1
        if lc=='success' or rc=='success':continue
        cross[(lc,rc)]+=1;coverage[cov]+=1
        rows.append(dict(identity=rec['identity'],family=rec['family'],coverage=cov,training_family_inputs=families[rec['family']],represented_observations=rec['observations'],left_category=lc,right_category=rc,source_facts=len(s['source']),effect_counts=dict(Counter(op['kind'] for op in rec['rule']['effects'])),left_body_rmse=l['body_rmse'],right_body_rmse=r['body_rmse']))
    result=dict(scope='held-out common-failure diagnosis, not a training set or native mutation audit',manifest_sha256=mh,left_model_sha256=left['model_sha256'],right_model_sha256=right['model_sha256'],artifact_sha256={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in (a.left,a.right)},cases=len(pairs),common_failures=len(rows),common_failure_coverage=dict(coverage),all_input_coverage=dict(all_coverage),common_failure_categories=[dict(left=l,right=r,count=n) for (l,r),n in sorted(cross.items())],all_outcomes=[dict(left=l,right=r,count=n) for (l,r),n in sorted(outcomes.items())],common_failure_rows=rows)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='common_failure_rows'},indent=2))

if __name__=='__main__':main()
