#!/usr/bin/env python3
"""Keep compiled source effects, charged costs, and remaining query obligations."""
import argparse
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def collect(root, output):
    validation = {}
    for suffix in ('workspace-tests', 'tests', 'non-sparse-tests'):
        log = (root / f'compiled-effects-{suffix}.log').read_text()
        assert 'test result: FAILED' not in log
        rows = [tuple(map(int, row)) for row in re.findall(
            r'test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored', log)]
        assert rows and sum(row[1] for row in rows) == 0
        validation[suffix] = dict(zip(('passed', 'failed', 'ignored'), map(sum, zip(*rows))))
    minimal = (root / 'compiled-effects-minimal-check.log').read_text()
    assert 'Finished' in minimal and 'error:' not in minimal
    validation['no_default_features'] = 'compile check passed'
    negative = (root / 'compiled-effects-arithmetic-negative.log').read_text()
    assert 'compiled_arithmetic_keys_select_the_actual_mutable_collision_result ... FAILED' in negative
    assert 'left: Number(1)' in negative and 'right: 0' in negative
    validation['negative_control'] = {
        'mutation': 'evaluate the compiled multiply expression as addition',
        'failure': 'the preview probes a different key and incorrectly admits a mutable collision as a birth',
        'production_source_restored_and_positive_suites_passed': True,
    }
    write(output / 'compiled-effects-validation.json', validation)

    audit = read(root / 'compiled-effects-final-audit/results.json')
    lanes = audit['cases']['sum-bits']['lanes']
    new = lanes['pure_epochs']
    old = read(output / 'displaced-epochs-audit.json')
    assert all(lane['hashes'] == old['hashes'] for lane in lanes.values())
    assert new['runs'] == 1428 and not new['scoped_executor']['global_observer']
    assert new['port_completion'] == old['port_completion']
    assert new['scoped_completion']['stats'] == old['scoped_completion']['stats']
    before, after = old['scoped_executor']['stats'], new['scoped_executor']['stats']
    expected = {'bound_rhs_ops': 65, 'bound_rhs_value_slots': 155,
                'bound_rhs_scratch_growths': 3, 'bound_rhs_expression_steps': 155,
                'bound_rhs_input_reads': 105}
    for key, value in after.items():
        assert value == expected.get(key, before.get(key)), (key, value)
    compiled = {k: v for k, v in new['scoped_completion']['plan'].items() if k.startswith('pure_rhs_')}
    assert compiled['pure_rhs_templates'] == 59 and compiled['pure_rhs_copies_elided'] == 72
    assert lanes['staged_scopes']['scoped_completion']['plan']['pure_rhs_templates'] == 0
    tables = [t['name'] for t in read(root / 'sum-program.json')['recipe']['tables']]
    waits = []
    for line in (root / 'compiled-effects-final-audit/sum-bits-pure_epochs.log').read_text().splitlines():
        if '[cell-cpu] completion-query ' not in line:
            continue
        wait = json.loads(line.split('completion-query ', 1)[1])
        conflicts = sorted({(tables[a], tables[b]) for rule in wait['rules'] for a, b in rule['conflicts']})
        wait['rules'] = [r['rule'] for r in wait['rules']]
        wait['conflicting_tables'] = conflicts
        wait['table_version_advances'] = [[tables[t], n] for t, n in wait['table_version_advances']]
        waits.append(wait)
    assert [w['ordinal'] for w in waits] == [23, 79, 86, 169, 477, 581]
    assert [w['effective_unions'] for w in waits] == [9, 0, 1, 12, 0, 50]
    zero = [w for w in waits if w['effective_unions'] == 0]
    assert [w['table_version_advances'] for w in zero] == [[['TCons', 1]], [['Concat', 2]]]
    assert all(w['constructor_collisions'] == w['legacy_repairs'] == 0 for w in zero)
    write(output / 'compiled-effects-audit.json', {
        'scope': 'standalone single-thread Cell CPU; exact ordered trace audit, not timing',
        'previous_revision': '10ae5ece', 'runtime_sha256': audit['runtime_sha256'],
        'program_file_sha256': new['program_file_sha256'], 'runs': new['runs'],
        'hashes': new['hashes'], 'exact_ordered_semantics_match': True,
        'admitted_as_performance_improvement': False,
        'compiled_code': compiled,
        'changed_preview_counters': {
            k: {'before': before.get(k), 'after': after[k]} for k in expected
        },
        'counter_scope': 'Scratch growths are selected preview allocation events, not whole-execution allocations. Expression/input counters were previously unmetered, not zero-cost. Instruction counts exclude these newly explicit operand steps.',
        'unchanged': {
            'query_waits': after['query_completions'], 'rhs_waits': after['rhs_completions'],
            'effective_source_unions_while_pending': after['source_unions_while_pending'],
            'fact_births_while_pending': after['rhs_fact_births_while_pending'],
            'key_lookup_calls': new['key_lookup_calls'],
            'port_completion_counts': 'identical to previous revision',
            'completion_queue_counts': 'identical to previous revision',
        },
        'remaining_query_waits': waits,
        'interpretation': 'The old slot-map preview is replaced by shared compiler-derived expressions. Copies and whole-binding clones disappear; exact collision, lifecycle and boundary proofs remain. Waiting and logical completion counts do not improve this iteration.',
        'remaining': 'Runs 79/477 only advance one TCons and two Concat query versions after proving no collisions. Separate those publication obligations from congruence without losing snapshot completeness. Runtime influence walks, shared mutable ownership and actual worker execution remain open.',
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    collect(args.root, args.output)
