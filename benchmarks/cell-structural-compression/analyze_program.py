#!/usr/bin/env python3
"""Compare actual last-owner Program teardown, not serialized artifact sizes."""
import hashlib
import json
import sys
from pathlib import Path


def read(path):
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    fields = dict(data['program_fields'])
    if len(fields) != len(data['program_fields']):
        raise ValueError('duplicate owner label')
    if sum(fields.values()) != data['retained_program_teardown_bytes']:
        raise ValueError('field attribution does not reconcile with complete teardown')
    return data, fields, hashlib.sha256(raw).hexdigest()


def main():
    if len(sys.argv) != 4:
        raise SystemExit('usage: analyze_program.py ORIGINAL CURRENT OUTPUT')
    a, x, ah = read(sys.argv[1])
    b, y, bh = read(sys.argv[2])
    for key in ('runs', 'final_state_sha256'):
        if a[key] != b[key]:
            raise ValueError(f'mismatched {key}')
    rows = [{'owner': k, 'original': x.get(k, 0), 'current': y.get(k, 0),
             'delta': y.get(k, 0) - x.get(k, 0)} for k in sorted(x.keys() | y.keys())]
    delta = b['retained_program_teardown_bytes'] - a['retained_program_teardown_bytes']
    result = {
        'scope': 'actual standalone Cell runtime; post-execution last-owner release order, not inclusive independent field sizes',
        'runs': b['runs'], 'final_state_sha256': b['final_state_sha256'],
        'original_program_bytes': a['retained_program_teardown_bytes'],
        'current_program_bytes': b['retained_program_teardown_bytes'],
        'program_delta_bytes': delta,
        'current_graph_bytes': b['graph_owned_teardown_bytes'],
        'charged_graph_plus_positive_program_delta_bytes': b['graph_owned_teardown_bytes'] + max(0, delta),
        'changed_owners': [r for r in rows if r['delta']],
        'all_owners': rows,
        'inputs_sha256': {'original': ah, 'current': bh},
        'limitation': 'matching final state is only a diagnostic; use the full per-Run audit and semantic acceptance for correctness',
    }
    Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
