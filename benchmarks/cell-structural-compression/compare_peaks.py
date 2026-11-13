#!/usr/bin/env python3
"""Compare saved single-lane allocation traces, without rerunning a workload."""
import hashlib
import json
import pathlib
import sys

original, materialized, lean, output = map(pathlib.Path, sys.argv[1:])
lanes = {}
for label, path in zip(('original', 'materialized', 'lean'), (original, materialized, lean)):
    raw = path.read_bytes()
    data = json.loads(raw)
    lanes[label] = {k: v for k, v in data.items() if k != 'samples'}
    lanes[label]['trace_sha256'] = hashlib.sha256(raw).hexdigest()
    if len(data['samples']) != data['runs']:
        raise SystemExit('incomplete Run samples')
if len({d['final_state_sha256'] for d in lanes.values()}) != 1:
    raise SystemExit('final states differ')
if len({d['runs'] for d in lanes.values()}) != 1:
    raise SystemExit('Run counts differ')
result = {
    'scope': 'actual standalone Cell runtime process requested heap; not Graph-exclusive heap or RSS',
    'limitation': 'excludes source parse high water; net growth is not a Graph-only peak; final hashes do not replace ordered Run audits',
    'lanes': lanes,
    'peak_bytes_removed_by_optional_materialization': lanes['materialized']['execution_and_takeover_peak_bytes'] - lanes['lean']['execution_and_takeover_peak_bytes'],
    'lean_peak_bytes_above_original': lanes['lean']['execution_and_takeover_peak_bytes'] - lanes['original']['execution_and_takeover_peak_bytes'],
}
output.write_text(json.dumps(result, indent=2) + '\n')
