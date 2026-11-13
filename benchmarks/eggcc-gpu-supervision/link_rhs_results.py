"""Link actual returned Eq values to observed later inputs, without ownership claims.

One shared provider group per typed root avoids expanding all producer/consumer
pairs. Only adjacent nonempty observed Runs are linked. These records are
training-data evidence, never executable continuations or causal proofs.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from collect_observed_corpus import read_bytes
from summarize_rhs_results import summarize


def link(trace):
    summarize(trace)  # Requires actual RHS schema and Run/final reference audits.
    rules=trace['recipe']['rules']
    steps={s['ordinal']:s for s in trace['steps']}
    runs=trace['runs'];counts=Counter();windows=[]
    if any(a['ordinal']>=b['ordinal'] for a,b in zip(runs,runs[1:])):
        raise ValueError('unordered or duplicate Runs')
    for producer_run,consumer_run in zip(runs,runs[1:]):
        before,after=producer_run['ordinal'],consumer_run['ordinal']
        gap=list(range(before+1,after))
        if before not in steps or after not in steps:
            raise ValueError('missing Run metadata')
        # No claim that omitted activity preserves values: conservatively reject
        # any intervening Run with executed bindings OR a reported graph change.
        if any(i not in steps or steps[i]['executed_bindings'] or steps[i]['changed'] for i in gap):
            counts['unproved_gaps']+=1;continue
        counts['eligible_windows']+=1
        providers=defaultdict(list)
        for index,b in enumerate(producer_run['audit']['bindings']):
            if not b['rhs']['completed']:
                counts['incomplete_producers']+=1;continue
            slots={s['slot']:s for s in b['rhs']['slots']}
            for op,effect in enumerate(rules[b['rule']]['effects']):
                # Copies are aliases, not extra producers. Mutable reads/sets
                # and scalars are not linked by equal numerical value.
                if effect['kind']!='construct':continue
                counts['constructor_results_requested']+=1
                s=slots.get(effect['dst'])
                if s is None or 'unavailable' in s:
                    counts['unavailable_constructor_results']+=1;continue
                if 'eq_port' not in s:
                    counts['non_eq_constructor_results']+=1;continue
                p=s['eq_port'];key=(p['sort'],p['after_run'])
                providers[key].append(dict(binding=index,rule=b['rule'],operation=op,
                    slot=effect['dst'],identity=p['identity'],at_rhs=p['at_rhs'],
                    root_changed=p['at_rhs']!=p['after_run']))
                counts['available_constructor_results']+=1
        groups=[];group_ids={};consumers=[]
        for index,b in enumerate(consumer_run['audit']['bindings']):
            counts['consumer_applications_examined']+=1
            ports=[];matched=False;external={};groups_used=set()
            for p in b['eq_ports']:
                key=(p['sort'],p['before']);choices=providers.get(key)
                counts['consumer_eq_slots_examined']+=1
                if choices:
                    matched=True
                    if key not in group_ids:
                        group_ids[key]=len(groups)
                        groups.append(dict(sort=key[0],root=key[1],providers=choices))
                    gid=group_ids[key];groups_used.add(gid)
                    exact=any(c['identity']==p['identity'] for c in choices)
                    ports.append(dict(slot=p['slot'],group=gid,
                        identity=p['identity'],relation='same_identity' if exact else 'same_equivalence_class'))
                    counts['linked_consumer_eq_slots']+=1
                    counts['same_identity_slots' if exact else 'equivalent_identity_slots']+=1
                else:
                    eid=external.setdefault(key,len(external))
                    ports.append(dict(slot=p['slot'],external=eid,sort=p['sort']))
            if not matched:continue
            counts['linked_consumer_applications']+=1
            counts['external_classes:'+str(len(external))]+=1
            if external:counts['multi_entry_consumer_applications']+=1
            if steps[before]['ruleset']!=steps[after]['ruleset']:
                counts['cross_ruleset_consumer_applications']+=1
            possible={c['binding'] for gid in groups_used for c in groups[gid]['providers']}
            common=set.intersection(*[{c['binding'] for c in groups[gid]['providers']} for gid in groups_used])
            if len(groups_used)>1 and not common:
                counts['requires_multiple_observed_providers']+=1
            consumers.append(dict(binding=index,rule=b['rule'],ports=ports,
                external_classes=len(external),candidate_provider_applications=len(possible),
                observed_input_values=b['values']))
        if consumers:
            counts['linked_windows']+=1
            counts['shared_provider_groups']+=len(groups)
            counts['stored_provider_references']+=sum(len(g['providers']) for g in groups)
            windows.append(dict(producer_run=before,consumer_run=after,
                producer_ruleset=steps[before]['ruleset'],consumer_ruleset=steps[after]['ruleset'],
                unchanged_intervening_runs=gap,groups=groups,consumers=consumers))
    return dict(schema='observed-rhs-input-links/v1',program_sha256=trace['program_sha256'],
        counts=dict(counts),windows=windows,causal_link_proven=False,takeover_authorized=False,
        limitations=['Actual equal identities are potential sources, not unique producers or causal links',
            'Consumer match establishes its input occurrence, not producer fact lifetime or ownership',
            'Only adjacent nonempty observed Runs with unchanged intervening Runs',
            'No linkage by scalar equality; mutable effects and copied aliases are not producers',
            'Consumer observations are future evidence, not producer prediction features'])


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--summary',type=Path);p.add_argument('--manifest',type=Path);a=p.parse_args()
    raw=read_bytes(a.trace);trace=json.loads(raw);result=link(trace)
    result['corpus_partition']=None
    if a.manifest:
        manifest_bytes=a.manifest.read_bytes();manifest=json.loads(manifest_bytes)
        entries=[e for e in manifest['cases'] if e.get('program_sha256')==result['program_sha256'] and e['status']=='complete']
        if len(entries)!=1:raise ValueError('ambiguous or missing corpus program')
        entry=entries[0];program=json.loads(read_bytes(Path(entry['program'])))
        if program['sha256']!=trace['program_sha256'] or program['recipe']!=trace['recipe']:
            raise ValueError('corpus recipe mismatch')
        result['corpus_partition']=dict(case=entry['case'],split=entry['split'],
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest())
    result['trace_sha256']=hashlib.sha256(raw).hexdigest()
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    if a.summary:
        report={k:v for k,v in result.items() if k!='windows'}
        report['links_sha256']=hashlib.sha256(a.output.read_bytes()).hexdigest()
        a.summary.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(result['counts']))

if __name__=='__main__':main()
