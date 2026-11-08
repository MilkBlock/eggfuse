#!/usr/bin/env python3
"""Retain ordered-publication regressions and charge the optional uniqueness proof."""
import argparse
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def changes(before, after):
    return {k: {'before': v, 'after': after[k]}
            for k, v in before.items() if after[k] != v}


def collect(root, output):
    validation = {}
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests'):
        log = (root / f'unique-publication-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and sum(row[1] for row in rows) == 0
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    minimal = (root / 'unique-publication-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    negatives = {}
    for suffix, test, description in (
        ('batch', 'early_publication_preserves_survivor_order_for_ordered_merge_observations',
         'Disable the remaining-unions guard. The first publication changes the survivor selected after the second union in the same batch.'),
        ('epochs', 'separate_source_epochs_preserve_ordered_merge_observations',
         'The previous pure-epoch proof admits overlapping constructor epochs. FactRef queue order then selects a different survivor than ordered source completion.'),
    ):
        log = (root / f'unique-publication-{suffix}-negative.log').read_text()
        assert f'{test} ... FAILED' in log and 'assertion `left == right` failed' in log
        assert 'TypeError' not in log
        records = re.findall(r'String\("record"\).*?Number\(0\).*?Number\((\d+)\)', log)
        assert records == ['12', '12'], records
        negatives[suffix] = description
    validation['negative_controls'] = negatives
    validation['negative_control_limit'] = 'Ordered exported witnesses differ; scalar record values stay equal in these fixtures. No differing numeric result is claimed.'
    write(output / 'unique-publication-validation.json', validation)

    audit = read(root / 'unique-publication-final-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    previous = read(output / 'compiled-effects-audit.json')
    assert all(lane['hashes'] == previous['hashes'] for lane in lanes.values())
    old, new = lanes['pure_epochs'], lanes['unique_publication']
    assert new['runs'] == 1428 and not new['scoped_executor']['global_observer']
    assert old['scoped_executor'] == new['scoped_executor']
    assert old['port_completion'] == new['port_completion']
    assert old['stats'] == new['stats'] and old['maintenance'] == new['maintenance']
    proof = new['stable_ports']['unique_publication']['stats']
    assert proof['accepted'] == proof['publications'] == 17
    assert old['stable_ports']['stats']['equality_enqueues'] == 1046
    assert new['stable_ports']['stats']['equality_enqueues'] == 1029
    charged = ('attempts', 'pending_checks', 'order_checks', 'anchor_reads',
               'signal_visits', 'static_steps', 'site_checks', 'operator_checks', 'publications')
    charged_events = sum(proof[k] for k in charged)
    assert charged_events == 7506
    counts = new['scoped_executor']['stats']
    assert (counts['query_completions'], counts['rhs_completions']) == (6, 4)
    assert counts['source_unions_while_pending'] == counts['rhs_fact_births_while_pending'] == 0
    tables = [t['name'] for t in read(root / 'sum-program.json')['recipe']['tables']]
    order_tables = {tables[int(t)]: n for t, n in new['port_completion']['stats']['pure_epoch_order_tables'].items()}
    fixture = read(root / 'unique-publication-fixture.json')
    point = fixture['checkpoint']
    assert not point['executor']['global_observer']
    assert (point['previous_pending'], point['current_pending']) == (1, 0)
    assert point['stable_ports']['stats']['equality_enqueues'] == 0
    write(output / 'unique-publication-fixture.json', fixture)
    write(output / 'unique-publication-audit.json', {
        'scope': 'standalone single-thread Cell CPU; exact ordered trace audit, not timing',
        'previous_revision': '3c5739e8', 'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'], 'runs': new['runs'],
        'hashes': new['hashes'], 'exact_ordered_semantics_match': True,
        'admitted_as_performance_improvement': False,
        'previous_admission_withdrawn': {
            'reason': 'A new regression disproves unrestricted overlap of pure constructor epochs under ordered survivor selection. The current conservative proof requires disjoint affected operator closures.',
            'query_waits': {'before': 6, 'after': 6},
            'rhs_waits': {'before': 0, 'after': 4},
            'effective_source_unions_while_pending': {'before': 5, 'after': 0},
            'fact_births_while_pending': {'before': 6, 'after': 0},
            'rejected_overlap_tables': order_tables,
            'limit': 'This does not establish that all four sum-bits batches intrinsically require a wait. Their previous proof was insufficient; finer independence remains unproved.',
        },
        'proof': proof, 'new_charged_proof_events': charged_events,
        'charged_proof_fields': charged,
        'stable_port_changes': changes(old['stable_ports']['stats'], new['stable_ports']['stats']),
        'condition_changes': changes(old['stable_ports']['local_conditions']['stats'], new['stable_ports']['local_conditions']['stats']),
        'queue_changes': changes(old['scoped_completion']['stats'], new['scoped_completion']['stats']),
        'unchanged': {
            'query_waits': 6, 'rhs_waits': 4,
            'influence_forecasts': new['port_completion']['stats']['forecasts'],
            'influence_scratch_growths': new['port_completion']['stats']['scratch_growths'],
            'key_lookup_calls': new['key_lookup_calls'],
            'candidate_buffer_growths': new['stable_ports']['local_conditions']['stats']['candidate_buffer_growths'],
            'ordinary_runtime_and_legacy_maintenance': True,
        },
        'interpretation': 'The optional path removes 17 queue obligations but none of the observed waits. It adds 7506 charged proof events and more head probes/port reads; the runtime domain walk is not admitted as an optimization.',
        'cost_limit': 'Counters describe selected operations and growth events, not measured latency or whole-execution allocations. Diagnostic maps and existing queue allocators are not a full allocator census.',
        'remaining': 'Bake/compiler must prove smaller independent regions and publication order without repeated domain walks. Unknown boundaries retain completion; shared mutable Graph state and actual workers remain open.',
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
