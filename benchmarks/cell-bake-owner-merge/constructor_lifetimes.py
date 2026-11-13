#!/usr/bin/env python3
"""Replay diagnostic receipt events; never infer unobserved RHS execution."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


def fact(value):
    if set(value) != {'cell', 'op'}:
        raise ValueError('unsupported fact address')
    return value['cell'], value['op']


def analyze(archive):
    if archive.get('schema') != 'cell-receipt-lifetime-trace/v1':
        raise ValueError('unsupported receipt archive')
    if archive.get('complete_archive') is not True or archive['trace']['dropped'] != 0:
        raise ValueError('incomplete receipt archive')
    if 'constructor_coverage' not in archive:
        raise ValueError('archive predates constructor outcome observation')
    counts = Counter()
    births = {}
    last_run = -1
    for item in archive['trace']['events']:
        run, event = item['run'], item['event']
        if run < last_run:
            raise ValueError('Run ordering reversed')
        last_run = run
        if event['kind'] == 'constructor':
            site = fact(event['site'])
            witness = event['witness']
            target = fact(witness['Fact']) if set(witness) == {'Fact'} else None
            if event['created']:
                if target != site or not event['visible']:
                    raise ValueError('invalid constructor birth')
                if site in births:
                    raise ValueError('second birth without observed retirement')
                births[site] = run
                counts['observed_births'] += 1
            else:
                counts['observed_reuses'] += 1
                counts['visible_reuses' if event['visible'] else 'hidden_reuses'] += 1
                if target is None:
                    counts['non_fact_reuses'] += 1
                elif target == site:
                    counts['same_fact_reuses'] += 1
                elif target[0] == site[0]:
                    counts['same_source_other_operation_reuses'] += 1
                else:
                    counts['foreign_source_reuses'] += 1
                if target in births:
                    counts['reuse_of_observed_prior_run_birth' if births[target] < run
                           else 'reuse_of_observed_same_run_birth'] += 1
                else:
                    counts['reused_target_birth_unobserved'] += 1
        elif event['kind'] == 'retire':
            receipt = event['fact']
            target = fact(receipt['Fact']) if set(receipt) == {'Fact'} else None
            if target in births:
                birth_run = births.pop(target)
                counts['observed_births_later_retired'] += 1
                counts['retired_across_runs' if birth_run < run else 'retired_same_run'] += 1
            else:
                counts['retirements_without_observed_birth'] += 1
    counts['observed_births_without_later_retirement_event'] = len(births)
    if counts['observed_births'] != counts['observed_births_later_retired'] + len(births):
        raise ValueError('birth accounting')
    return dict(scope='Observed constructor outcomes only; missing fast paths and aliases remain unknown',
                coverage=archive['constructor_coverage'], counts=dict(counts),
                limitations=[
                    'No retirement event does not prove final liveness or visibility.',
                    'Foreign reuse is an actual result address, not permission to reuse it in a later stage.',
                    'Unobserved nominal operations cannot be classified from this archive.',
                ])


def template_transitions(archive):
    """Group actual live-birth reuse edges, never reconstruct retired templates."""
    analyze(archive)  # Same ordering, loss and birth/retirement checks.
    if archive.get('constructor_identity') != 'source-template-operation/v1':
        raise ValueError('requires recorded source template identities')
    births, groups = {}, Counter()
    unknown = Counter()
    for item in archive['trace']['events']:
        event, run = item['event'], item['run']
        if event['kind'] == 'retire':
            receipt = event['fact']
            if set(receipt) == {'Fact'}:
                births.pop(fact(receipt['Fact']), None)
            continue
        if event['kind'] != 'constructor':
            continue
        template = event.get('template')
        if template is not None and (type(template) is not int or template < 0):
            raise ValueError('invalid recorded source template')
        site, table = fact(event['site']), event['table']
        if event['created']:
            births[site] = (run, template, table)
            continue
        if not event['visible']:
            unknown['hidden_result'] += 1
            continue
        witness = event['witness']
        target = fact(witness['Fact']) if set(witness) == {'Fact'} else None
        producer = births.get(target)
        if producer is None:
            unknown['unobserved_live_birth'] += 1
            continue
        born, source_template, source_table = producer
        if source_table != table:
            raise ValueError('constructor reuse changes table identity')
        if template is None or source_template is None:
            unknown['unobserved_source_template'] += 1
            continue
        groups[(source_template, target[1], template, site[1], table,
                'cross_run' if born < run else 'same_run')] += 1
    return dict(scope='actual visible constructor reuse with observed live birth; not a closure certificate',
        transitions=[dict(producer_template=p, producer_op=po, consumer_template=c,
                          consumer_op=co, table=t, stage=stage, uses=count)
                     for (p,po,c,co,t,stage),count in sorted(groups.items())],
        unknown=dict(unknown))


def missing_membership(report):
    # Caller must first validate the complete, current observer archive.
    latest, retirements = {}, {}
    for index, item in enumerate(report['receipt_trace']['trace']['events']):
        event = item['event']
        if event['kind'] == 'constructor':
            latest[fact(event['site'])] = (index, event)
        elif event['kind'] == 'retire' and set(event['fact']) == {'Fact'}:
            retirements[fact(event['fact']['Fact'])] = index
    ownership = report['ownership_storage']
    layouts = {}
    for component in ownership['components']:
        shape = ownership['shapes'][component['shape']]
        for ordinal, cell in enumerate(component['frames']):
            if cell in layouts:
                raise ValueError('duplicate composition identity')
            layouts[cell] = ownership['programs'][shape['programs'][ordinal]]['fields']
    counts = Counter()
    for frame in report['source_storage']['fact_lifecycle']['frames']:
        if not frame['completed_storage']:
            continue
        present = {f['op'] for f in frame['facts']}
        for op, fields in enumerate(layouts[frame['cell']]):
            if not fields or op in present:
                continue
            counts['absent_owned_positions'] += 1
            site = frame['cell'], op
            observed = latest.get(site)
            if observed is None:
                reason = 'no_constructor_outcome_observed'
            else:
                index, event = observed
                target = fact(event['witness']['Fact']) if set(event['witness']) == {'Fact'} else None
                if target != site:
                    reason = 'last_result_was_another_fact_or_function'
                elif retirements.get(site, -1) > index:
                    reason = ('created_locally_then_retired' if event['created']
                              else 'returned_local_fact_then_retired')
                else:
                    reason = 'local_result_absence_unexplained'
            counts[reason] += 1
    if sum(v for k, v in counts.items() if k != 'absent_owned_positions') != counts['absent_owned_positions']:
        raise ValueError('missing-position accounting')
    return dict(counts)


def batch(report):
    rows = []
    for case in report['cases']:
        if case['all_saved_run_checks_equal'] is not True or case['terminal_check_equal'] is not True:
            raise ValueError('missing execution differential validation')
        observed = analyze(case['receipt_trace'])
        observed.update(case=case['case'], program=case['program'], runs=case['runs'],
                        all_saved_run_checks_equal=True, terminal_check_equal=True,
                        missing_membership=missing_membership(case))
        if case["receipt_trace"].get("constructor_identity") == "source-template-operation/v1":
            observed["template_transitions"] = template_transitions(case["receipt_trace"])
        rows.append(observed)
    return dict(scope='Actual standalone Cell runtime with diagnostic trace; no speed/native acceptance claim', cases=rows)


if __name__ == '__main__':
    raw = Path(sys.argv[1]).read_bytes()
    report = json.loads(raw)
    result = batch(report) if 'cases' in report else analyze(report.get('receipt_trace', report))
    result['input_sha256'] = hashlib.sha256(raw).hexdigest()
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
