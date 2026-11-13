#!/usr/bin/env python3
"""Audit installed catalog families without treating wiring as execution history."""
import hashlib
import json
import sys
from pathlib import Path

rows = []
for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
    path = Path(sys.argv[1]) / name / 'candidate.json'
    data = path.read_bytes()
    raw = json.loads(data)
    iterative = raw.get('iterative_bake') or {}
    rows.append(dict(case=name, input_sha256=hashlib.sha256(data).hexdigest(),
        program=raw['sha256'],
        ownership_fragments=len(raw.get('ownership_fragments', {}).get('fragments', [])),
        witness_recipes=len(raw.get('ownership_witnesses', {}).get('recipes', [])),
        spine_entries=len((raw.get('spine_blocks') or {}).get('entries', [])),
        iterative_installed=bool(iterative), iterative_joins=len(iterative.get('joins', [])),
        result_switch_installed=bool(iterative.get('rhs_handoffs'))))
Path(sys.argv[2]).write_text(json.dumps(dict(
    scope='Artifact presence only; ordinary cross-stage Shared Entry and composition may still execute without iterative_bake',
    cases=rows), indent=2) + '\n')
for row in rows:
    print(row['case'], row['ownership_fragments'], row['witness_recipes'], row['iterative_installed'])
