"""Exact CPU growth diagnosis of the same synthetic entry as the GPU audit.

Uses the compiler recipe, never real Run bindings. A budget end is not proof
of nontermination. Results do not train or correct the GPU model.
"""
import argparse,json,hashlib,time
from collections import Counter
from copy import deepcopy
from pathlib import Path
from device_stage_models import select_ruleset
from neural_cell_samples import samples
from neural_cell_chains import chains


def audit(recipe,reference,rounds,fact_limit):
    ref=deepcopy(reference);logs=[];started=time.perf_counter();status='round_budget'
    initial=sorted(ref.normalized_facts())
    for turn in range(rounds):
        before=ref.constructions;unions=ref.unions;previous=ref.normalized_facts()
        delta,applications=ref.apply(recipe['rules'])
        logs.append(dict(round=turn+1,applications=applications,per_rule_applications=ref.last_match_counts,
            new_constructors=ref.constructions-before,new_unions=ref.unions-unions,
            facts=len(ref.normalized_facts()),tables=dict(Counter(t for t,v in ref.normalized_facts())),
            new_normalized_facts=sorted(ref.normalized_facts()-previous)))
        if not delta:status='fixedpoint';break
        if len(ref.normalized_facts())>=fact_limit:status='fact_budget';break
    nullary={}
    for table,values in initial:
        if len(values)==1:nullary.setdefault(values[0],[]).append(table)
    return dict(scope='exact standalone CPU reference with all matches before each Run; not native egglog or GPU execution',
                status=status,logs=logs,initial_facts=initial,
                aliased_nullary_constructors=[dict(root=k,tables=v) for k,v in sorted(nullary.items()) if len(v)>1],
                wall_seconds=time.perf_counter()-started)


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--ruleset',default='canon');p.add_argument('--pair',nargs=2,type=int,default=[5,7])
    p.add_argument('--all-pairs',action='store_true')
    p.add_argument('--rounds',type=int,default=12);p.add_argument('--fact-limit',type=int,default=512);a=p.parse_args()
    if a.rounds<1 or a.fact_limit<1:raise ValueError('positive budgets required')
    source=json.loads(a.trace.read_text());recipe,manifest=select_ruleset(source.get('recipe',source),a.ruleset)
    records=[];samples(recipe,4,93003,records,ordered=True);transfers=[]
    data,_=chains(recipe,records,ordered=True,transfers=transfers,include_uncovered_transfers=True)
    entries={}
    for r in transfers:
        pair=(int(data['producer'][r['chain']]),int(data['consumer'][r['chain']]))
        entries.setdefault(pair,r)
    if a.all_pairs:
        cases=[dict(pair=list(pair),**audit(recipe,r['reference'],a.rounds,a.fact_limit)) for pair,r in entries.items()]
        result=dict(scope='exact CPU reference termination census for all selected synthetic pairs',cases=cases,
                    statuses=dict(Counter(c['status'] for c in cases)))
    else:
        result=audit(recipe,entries[tuple(a.pair)]['reference'],a.rounds,a.fact_limit);result['pair']=a.pair
    result.update(stage_manifest=manifest,sample_seed=93003,samples_per_rule=4,
        recipe_sha256=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest())
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
