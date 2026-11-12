#!/usr/bin/env python3
"""Compare complete-domain work and both representations of class certificates."""
import copy
import json
import sys
from pathlib import Path


def analyze(root):
    def load(name):
        return json.loads((root / name).read_text())
    artifacts = [load(p + '/program.json') for p in
                 ('closure-existing', 'domain-classes-program', 'domain-classes-derived')]
    normalized = []
    for raw in artifacts:
        raw = copy.deepcopy(raw)
        raw.pop('sha256')
        raw['ownership_fragments'].pop('query_classes', None)
        normalized.append(raw)
    if not all(x == normalized[0] for x in normalized):
        raise ValueError('source or execution catalog changed beyond optional query classes')
    audits = [load(name + '-audit.json') for name in
              ('domain-only', 'domain-coverage', 'domain-classes-derived')]
    for i, run in enumerate(audits):
        if not run['all_saved_run_checks_equal'] or run['runs'] != audits[0]['runs']:
            raise ValueError('Run acceptance missing')
        if run['program_sha256'] != artifacts[2 if i == 2 else 0]['sha256']:
            raise ValueError('audit/artifact identity mismatch')
        if run['final_state'] != audits[0]['final_state']:
            raise ValueError('final state differs')
    work = ['domain_legacy_visits', 'domain_signal_visits', 'domain_slice_steps', 'domain_results',
            'domain_type_guards', 'query_class_probes', 'query_class_range_jumps']
    work += ['key_candidates', 'key_field_comparisons']
    rows = []
    for name, audit in zip(('prior', 'coverage', 'classes'), audits):
        values = audit['measured_work']
        rows.append({'mode': name, 'program_sha256': audit['program_sha256'], 'work': {
            k: values[('stable_ports/stats/' if k.startswith('key_') else 'cell_ownership/stats/') + k]
            for k in work}})
    heaps = [load(name + '-heap.json') for name in
             ('domain-only', 'domain-classes', 'domain-classes-derived')]
    for i, heap in enumerate(heaps):
        if heap['program_sha256'] != artifacts[i]['sha256'] or heap['runs'] != audits[0]['runs']:
            raise ValueError('heap/artifact identity mismatch')
        if heap['final_state_sha256'] != heaps[0]['final_state_sha256']:
            raise ValueError('heap final state differs')
    return {'scope': 'actual standalone Cell runtime; work and requested heap, not timing',
            'runs': audits[0]['runs'], 'all_saved_run_checks_equal': True,
            'only_optional_classes_changed': True, 'final_states_equal': True,
            'work': rows,
            'memory': [{'mode': mode, **{k: h[k] for k in ('graph_owned_teardown_bytes',
                'retained_program_teardown_bytes', 'execution_and_takeover_peak_bytes')}}
                for mode, h in zip(('no_classes', 'materialized_classes', 'derived_classes'), heaps)],
            'limitations': ['materialized classes have a final-state heap observation, not a separate full Run audit',
                           'extra candidate and compiled storage costs are reported; no speedup claimed',
                           'facts and RHS effects remain unchanged']}


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: analyze_domain_coverage.py ARTIFACT_ROOT OUTPUT')
    result = analyze(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
