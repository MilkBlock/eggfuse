"""Conditional local completion targets from actual matched input states.

Uses only pre-Run Eq partitions and scalar inputs to construct model inputs.
Post-Run identities check derived input equalities; they never encode features.
This is not a capture of full constructor outputs or global novelty/saturation.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
from dominator_completion import compose,freeze


def instantiate(rule,binding,tables):
    ports={p['slot']:p for p in binding['eq_ports']};groups={};env={}
    for item in sorted(binding['values'],key=lambda x:x['slot']):
        slot=item['slot'];value=item['value'];sort=rule['slots'][slot]['sort']
        if sort['kind']=='eq':
            if slot not in ports:raise ValueError('missing audited Eq port')
            p=ports[slot]
            if p['sort']!=sort['name']:raise ValueError('Eq sort mismatch')
            key=(p['sort'],p['before'])
            env[slot]=('observed',sort['name'],groups.setdefault(key,len(groups)))
        elif sort['kind'] in ('i64','bool','String'):
            env[slot]=('literal',json.dumps(dict(literal=value['value'],sort=sort),sort_keys=True))
        else:return None,'unsupported observed scalar: '+sort['kind']
    source=[]
    for atom in rule['query']:
        name=atom['call'].get('table')
        if tables.get(name,{}).get('kind')!='constructor':return None,'non-constructor premise'
        values=[]
        for a in atom['args']:
            if 'slot' in a:
                if a['slot'] not in env:raise ValueError('missing observed query slot')
                values.append(env[a['slot']])
            else:values.append(('literal',json.dumps(a,sort_keys=True)))
        source.append((name,tuple(values)))
    inputs=sorted(env.items())
    completion,reason=compose(source,rule,inputs,tables)
    if reason:return None,reason
    return dict(source=source,binding=inputs,completion=completion),None


def equality_audit(sample,binding):
    env=dict(sample['binding']);quotient={freeze(a):freeze(b) for a,b in sample['completion']['source_map']}
    checked=0;violations=0
    for i,a in enumerate(binding['eq_ports']):
        for b in binding['eq_ports'][:i]:
            if a['sort']!=b['sort'] or a['before']==b['before']:continue
            x,y=env[a['slot']],env[b['slot']]
            if x not in quotient or y not in quotient:continue
            if quotient[x]==quotient[y]:
                checked+=1;violations+=a['after']!=b['after']
    return checked,violations


def collect(program,trace):
    if trace['program_sha256']!=program['sha256']:raise ValueError('program mismatch')
    if not trace['strict_audit_reference_equal'] or not trace['run_control_counts_equal']:raise ValueError('unaudited trace')
    recipe=program['recipe'];tables={t['name']:t for t in recipe['tables']};rows=[];seen={};marks=Counter();counts=Counter();patterns=defaultdict(set);total=checked=violations=0
    for run in trace['runs']:
        for ordinal,b in enumerate(run['audit']['bindings']):
            total+=1;rid=b['rule'];sample,reason=instantiate(recipe['rules'][rid],b,tables)
            if reason:marks[reason]+=1;continue
            count,bad=equality_audit(sample,b);checked+=count;violations+=bad
            key=json.dumps((rid,sample['source'],sample['binding']),sort_keys=True)
            patterns[rid].add(key);counts[rid]+=1
            if key in seen:
                rows[seen[key]]['observations']+=1
                continue
            seen[key]=len(rows)
            rows.append(dict(producer=rid,consumer=rid,**sample,observations=1,first_run=run['ordinal'],first_binding=ordinal,source_run_validated=False))
    return dict(schema='observed-local-cell-targets/v1',program_sha256=program['sha256'],targets=rows,
        summary=dict(observed_bindings=total,supported_bindings=sum(counts.values()),unique_states=len(rows),represented_rules=len(patterns),rules_with_multiple_states=sum(len(v)>1 for v in patterns.values()),maximum_states_per_rule=max(map(len,patterns.values()),default=0),marks=dict(marks),derived_input_equalities_checked=checked,derived_input_equality_violations=violations),
        limitations=['Inputs originate in real pre-Run successful bindings, not GPU matching','Labels are conditional local constructor/union completion, not observed full runtime output','Novel means locally added information; global constructor reuse or global novelty not established','Post-Run check covers only derived input Eq pairs, not constructor outputs or source visibility','Repeated identical input states deduplicated; observations retain their frequency','No full-stage GPU runtime or ownership transfer authorization'])


def main():
    p=argparse.ArgumentParser();p.add_argument('program',type=Path);p.add_argument('trace',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    result=collect(json.loads(args.program.read_text()),json.loads(args.trace.read_text()))
    result['trace_sha256']=hashlib.sha256(args.trace.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary'],indent=2))
    if result['summary']['derived_input_equality_violations']:raise SystemExit('derived equality rejected by native post-Run audit')

if __name__=='__main__':main()
