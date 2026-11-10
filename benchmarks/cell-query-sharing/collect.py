#!/usr/bin/env python3
"""Validate saved Cell query overlap observations without executing workloads."""
import argparse
import hashlib
import json
from pathlib import Path

RUN = ['ordinal', 'ruleset', 'path', 'iterations', 'epoch', 'logical_matches', 'executed_bindings', 'changed']


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def compare(before, after, program):
    a, b, p = read(before / 'report.json'), read(after / 'report.json'), read(program)
    assert a['program_sha256'] == b['program_sha256'] == p['sha256']
    assert sha(before / 'state.json') == sha(after / 'state.json')
    runs = lambda r: [[s[k] for k in RUN] for s in r['steps']]
    assert runs(a) == runs(b)
    assert a['stats'] == b['stats']
    assert a['key_lookup_calls'] == b['key_lookup_calls']
    q = b['query_workers']['stats']
    d = q['sharing_audit']
    assert d['entries'] == q['spine_entries']
    assert d['point_reads'] == q['spine_point_reads']
    assert d['successful_entries'] + d['rejected_entries'] == d['entries'] and d['error_entries'] == 0
    assert d['distinct_read_keys'] + d['cross_entry_repeated_reads'] + d['same_entry_repeated_reads'] == d['point_reads']
    assert sum(d['repeated_read_pairs'].values()) == d['cross_entry_repeated_reads']
    assert d['repeated_reads_in_successful_entries'] + d['repeated_reads_in_rejected_entries'] == d['cross_entry_repeated_reads']
    assert d['same_anchor_prefix_reads'] + d['same_anchor_prefix_guards'] == d['same_anchor_prefix_steps']
    pairs = []
    for pair, count in sorted(d['repeated_read_pairs'].items(), key=lambda kv: (-kv[1], kv[0])):
        template, old_rule, old_pivot, new_rule, new_pivot, table = map(int, pair.split(':'))
        name = p['recipe']['tables'][table]['name']
        rule = p['recipe']['rules'][new_rule]
        atoms = [(i, atom) for i, atom in enumerate(rule['query']) if atom['call'].get('table') == name]
        # Only attribute a pair to a literal key when its table has exactly
        # one query atom. More general pairs need an instruction-level proof.
        literal_key = len(atoms) == 1 and all('literal' in arg for arg in atoms[0][1]['args'][:-1])
        pairs.append({'producer_template': template, 'producer_source_set': p['recipe']['rules'][template]['metadata']['source_set'],
                      'first_rule_pivot': [old_rule, old_pivot], 'repeat_rule_pivot': [new_rule, new_pivot],
                      'table': name, 'count': count, 'unambiguous_literal_key': literal_key})
    return {'program_sha256': p['sha256'], 'program_file_sha256': sha(program),
            'runs': len(runs(b)), 'state_sha256': sha(after / 'state.json'),
            'run_signature_sha256': hashlib.sha256(json.dumps(runs(b)).encode()).hexdigest(),
            'reports': {'before': sha(before / 'report.json'), 'audit': sha(after / 'report.json')},
            'counts': d, 'read_pairs': pairs,
            'literal_key_repeated_reads': sum(row['count'] for row in pairs if row['unambiguous_literal_key']),
            'same_core_work': True}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['root', 'sum_program', 'ray_program', 'ray_before', 'output']:
        p.add_argument(name, type=Path)
    a = p.parse_args()
    provenance = read(a.root / 'provenance.json')
    for name, digest in provenance['binaries'].items():
        assert sha(a.root / name) == digest
    checks = read(a.root / 'checks/checks.json')
    assert checks['semantic_acceptance']['status'] == 'pass'
    assert checks['binaries']['candidate'] == provenance['binaries']['runtime-audit']
    assert checks['binaries']['baseline'] == provenance['baseline_runtime_sha256']
    cases = {'sum': compare(a.root / 'sum-before', a.root / 'sum4', a.sum_program),
             'ray128': compare(a.ray_before, a.root / 'ray128', a.ray_program)}
    inline = compare(a.root / 'sum-before', a.root / 'sum1', a.sum_program)
    assert inline['counts'] == cases['sum']['counts']
    result = {'scope': 'Standalone Cell CPU; opt-in cell-query-sharing-audit; short executions, not speed or takeover.',
              'provenance': provenance, 'semantic_acceptance': 'pass', 'checks_sha256': sha(a.root / 'checks/checks.json'),
              'cases': cases, 'sum_inline_and_pool_counts_equal': True,
              'limits': 'The diagnostic clones keys and anchors into per-chunk maps. It never serves a query result. '
                        'Normal builds contain none of those maps or diagnostic headers. '
                        'Same-anchor prefix repeats are a conservative subset of possible shared expressions; '
                        'zero does not exclude sharing across distinct anchors. Dynamic duplicate reads are '
                        'opportunities, not saved operations. Missing/default, visibility, Eq, per-entry tests, '
                        'watermark, delta ownership and source order remain authoritative. No full Raytrace inference.'}
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: {k: row[k] for k in ['literal_key_repeated_reads', 'runs']} for name, row in cases.items()}, indent=2))


if __name__ == '__main__':
    main()
