"""Measure finite Cell-family coverage before fitting a larger ridge model."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
from collect_observed_corpus import read_bytes,role_features


def key(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def template_key(rule):
    # Conservative compiler-layout identity; not semantic egraph equivalence.
    return key(dict(query=rule['query'],effects=rule['effects'],sorts=[s['sort'] for s in rule['slots']]))


def profile(manifest):
    records=[];marks=Counter();failures=[];pending=[];role_targets=defaultdict(set);role_occurrences=Counter();role_examples=defaultdict(dict);position_targets=defaultdict(set);recorded_role_mismatches=0
    for row in manifest['cases']:
        if row['status']=='pending':pending.append(row['case']);continue
        if row['status']!='complete':failures.append(dict(case=row['case'],error=row.get('error')));continue
        program=json.loads(read_bytes(Path(row['program'])))
        data=json.loads(Path(row['targets']).read_text());marks.update(data['summary']['marks'])
        for sample in data['targets']:
            rule=program['recipe']['rules'][sample['consumer']];family=template_key(rule)
            inputs=key((family,sample['source'],sample['binding']))
            roles=role_features(rule,sample['binding'])
            if sample.get('input_local_roles')!=json.loads(json.dumps(roles)):recorded_role_mismatches+=1
            role_pattern=key((family,roles))
            target_key=key(sample['completion'])
            positioned=role_features(rule,sample['binding'],positions=True)
            position_targets[key((family,positioned))].add(target_key)
            role_targets[role_pattern].add(target_key)
            if target_key not in role_examples[role_pattern] and len(role_examples[role_pattern])<2:
                role_examples[role_pattern][target_key]=dict(case=row['case'],rule=sample['consumer'],source=sample['source'],binding=sample['binding'],completion=sample['completion'])
            role_occurrences[role_pattern]+=sample['observations']
            records.append((row['split'],family,inputs,role_pattern,sample['observations']))
    training_families={r[1] for r in records if r[0]=='train'}
    training_inputs={r[2] for r in records if r[0]=='train'}
    training_roles={r[3] for r in records if r[0]=='train'}
    reports={}
    for part in ('train','validation','test'):
        selected=[r for r in records if r[0]==part]
        reports[part]=dict(observations=sum(r[4] for r in selected),unique_families=len({r[1] for r in selected}),unique_input_states=len({r[2] for r in selected}),unique_role_patterns=len({r[3] for r in selected}),
            observations_in_training_family=sum(r[4] for r in selected if r[1] in training_families),
            observations_with_exact_training_input=sum(r[4] for r in selected if r[2] in training_inputs),
            observations_with_training_role_pattern=sum(r[4] for r in selected if r[3] in training_roles))
    families=defaultdict(set)
    for _,family,inputs,_,_ in records:families[family].add(inputs)
    return dict(scope='real observed input coverage, not learned accuracy or exact saturation states',recorded_role_mismatches=recorded_role_mismatches,completed_workloads=sum(r['status']=='complete' for r in manifest['cases']),pending=pending,failures=failures,reports=reports,total_unique_families=len(families),families_with_multiple_input_states=sum(len(v)>1 for v in families.values()),largest_family_input_states=max(map(len,families.values()),default=0),role_patterns_with_multiple_exact_targets=sum(len(v)>1 for v in role_targets.values()),observations_in_ambiguous_role_patterns=sum(role_occurrences[k] for k,v in role_targets.items() if len(v)>1),positioned_role_patterns_with_multiple_exact_targets=sum(len(v)>1 for v in position_targets.values()),role_collision_examples=[dict(role_signature=k,examples=list(role_examples[k].values())) for k,v in role_targets.items() if len(v)>1][:8],marks=dict(marks),limitations=['Template identity is conservative compiler layout, not semantic alpha-equivalence','Exact input overlap is measured and reported, not treated as unseen-state success','Local roles include matched query and direct effect positions with copy aliases; no target facts','Full successor-state enumeration and off-manifold recovery are not measured here'])


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    result=profile(json.loads(args.manifest.read_text()));args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
