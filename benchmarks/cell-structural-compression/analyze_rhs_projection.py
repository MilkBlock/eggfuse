#!/usr/bin/env python3
"""Offline candidates only; equal post-completion projections are not skip proofs."""
import collections
import json
import sys
from pathlib import Path


def analyze(run):
    if not run['all_saved_run_checks_equal']:
        raise ValueError('Run validation missing')
    archive=run['rhs_projection_trace']
    if archive['schema']!='cell-rhs-projection-trace/v1' or not archive['complete_archive'] or archive['trace']['dropped']:
        raise ValueError('missing or incomplete projection archive')
    trace=archive['trace'];plans=trace['plans'];local={};global_seen={};counts=collections.Counter()
    rules=collections.defaultdict(collections.Counter);examples=[];last_run=0
    projection_seen={};guarded=collections.Counter();guarded_examples=[]
    for index,e in enumerate(trace['events']):
        if e['run']<last_run:raise ValueError('completion Run order regressed')
        last_run=e['run'];rule=e['rule'];plan=plans[rule]
        if plan is None or plan['rule']!=rule:raise ValueError('event without pure constructor plan')
        counts['observations']+=1;rules[rule]['observations']+=1
        if e['values'] is None:
            counts['unavailable_inputs']+=1;continue
        if len(e['values'])!=len(plan['slots']) or len(e['output_versions'])!=len(plan['tables']):
            raise ValueError('projection/version width mismatch')
        key=json.dumps([rule,e['union_revision'],e['output_versions'],e['values']],sort_keys=True)
        projection=json.dumps([rule,e['values']],sort_keys=True)
        if projection in projection_seen:
            prior_index,prior=projection_seen[projection]
            changed_union=prior['union_revision']!=e['union_revision']
            changed_table=prior['output_versions']!=e['output_versions']
            if changed_union or changed_table:
                boundary='cross_run' if prior['run']!=e['run'] else 'within_run'
                guarded[boundary]+=1
                guarded['new_facts']+=e['facts']
                guarded['function_updates']+=e['updates']
                guarded['union_requests']+=e['union_requests']
                guarded['constructor_requests']+=e['constructor_requests']
                guarded['union_revision_changed']+=changed_union
                guarded['table_version_changed']+=changed_table
                if len(guarded_examples)<8:
                    guarded_examples.append({'previous_index':prior_index,'index':index,'rule':rule,
                        'prior_run':prior['run'],'run':e['run'],'union_changed':changed_union,
                        'table_changed':changed_table,'new_facts':e['facts']})
        projection_seen[projection]=(index,e)
        scoped=(e['run'],key)
        previous=local.get(scoped,global_seen.get(key))
        kind='within_run' if scoped in local else 'cross_run' if key in global_seen else 'first'
        counts[kind]+=1;rules[rule][kind]+=1
        if kind!='first':
            mutation_free=e['facts']==e['updates']==e['union_requests']==0
            counts['repeated_constructor_requests']+=e['constructor_requests']
            rules[rule]['repeated_constructor_requests']+=e['constructor_requests']
            counts['mutation_free_repeats' if mutation_free else 'repeats_with_work']+=1
            if len(examples)<12:
                examples.append({'index':index,'previous_index':previous,'kind':kind,'mutation_free':mutation_free,**e})
        local[scoped]=index;global_seen[key]=index
    return {'scope':'actual standalone runtime, offline RHS reuse candidates, not executable completion proofs',
        'program_sha256':run['program_sha256'],'runs':run['runs'],'all_saved_run_checks_equal':True,
        'unsupported_completions':trace['unsupported_completions'],'dropped':trace['dropped'],
        'counts':dict(counts),'changed_revision_candidates':dict(guarded),
        'changed_revision_examples':guarded_examples,'rules':[{ 'rule':r,**dict(c)} for r,c in sorted(rules.items(),key=lambda x:-x[1]['repeated_constructor_requests'])],
        'examples':examples,'limitations':[
            'records are sampled after completion, not matching inputs before execution',
            'whole-table query versions split groups conservatively; changed-revision candidates need local proof, not global cache reuse',
            'single-write fast paths and already-direct completions are outside this pure-constructor observer',
            'publication, result ownership, delta ownership and history obligations are not discharged',
            'constructor requests are work attempts, not committed mutations',
            'no new reverse index or duplicate binding store is proposed for execution']}

if __name__=='__main__':
    if len(sys.argv) not in (3,4):raise SystemExit('usage: analyze_rhs_projection.py AUDIT OUTPUT [BASELINE]')
    current=json.loads(Path(sys.argv[1]).read_text())
    result=analyze(current)
    if len(sys.argv)==4:
        baseline=json.loads(Path(sys.argv[3]).read_text())
        for key in ('program_sha256','runs','all_saved_run_checks_equal','final_state','graph_work','source_storage'):
            if baseline[key]!=current[key]:raise ValueError('observer changes baseline '+key)
        result['baseline_state_and_graph_work_equal']=True
        result['observation_work_changes']={k:[baseline['measured_work'].get(k),v]
            for k,v in current['measured_work'].items() if baseline['measured_work'].get(k)!=v}
    Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rules','examples','limitations')}))
