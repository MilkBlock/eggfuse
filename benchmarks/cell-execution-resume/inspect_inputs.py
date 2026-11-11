#!/usr/bin/env python3
"""Identify later scalar sites whose data is available from matched inputs.

This is an offline opportunity inventory, not runtime authorization or a proof
that arithmetic cannot fail. Failed preparation must remain source-positioned.
"""
import hashlib
import json
from pathlib import Path
import sys


def inspect(program, report, output):
    p = json.loads(program.read_text())
    r = json.loads(report.read_text())
    assert p['sha256'] == r['program_sha256']
    allowed = {'+', '-', '*', '/', '%', 'min', 'max', '=', '!=', '<', '<=', '>', '>=',
               'not', 'and', 'or', 'xor', 'implies'}
    rows = []
    for rid, rule in enumerate(p['recipe']['rules']):
        slots = rule['slots']
        inputs = {i for i, s in enumerate(slots) if s['definition'] == 'query'}
        ready, boundary, sites = set(inputs), False, []
        def scalar(a):
            sort = slots[a['slot']]['sort'] if 'slot' in a else a['sort']
            return sort['kind'] in {'i64', 'bool', 'Unit'}
        def has(a):
            return 'slot' not in a or a['slot'] in ready
        for position, e in enumerate(rule['effects']):
            if e['op'] == 'copy':
                available = has(e['arg'])
                ready.discard(e['dst'])
                if available:
                    ready.add(e['dst'])
                continue
            primitive = e.get('call', {}).get('primitive')
            local = (e['op'] == 'let' and primitive in allowed
                     and e['sort']['kind'] in {'i64', 'bool', 'Unit'}
                     and e['dst'] not in inputs
                     and len(e['args']) == (1 if primitive == 'not' else 2)
                     and all(scalar(a) for a in e['args']))
            if local:
                possible = all(has(a) for a in e['args'])
                if boundary:
                    sites.append({'operation': position, 'input_closed': possible})
                if possible:
                    ready.add(e['dst'])
            else:
                boundary = True
                if e['op'] == 'let':
                    ready.discard(e['dst'])
        if sites:
            rows.append({'rule': rid, 'later_scalar_sites': sites,
                         'observed_spine_bindings': r['stage_spine']['stats']['bindings_by_rule'].get(str(rid), 0)})
    result = {
        'program_sha256': p['sha256'], 'report_sha256': hashlib.sha256(report.read_bytes()).hexdigest(),
        'rules': rows,
        'later_scalar_sites': sum(len(x['later_scalar_sites']) for x in rows),
        'input_closed_sites': sum(s['input_closed'] for x in rows for s in x['later_scalar_sites']),
        'limits': 'Candidate data availability only. Observed Spine bindings are a subset of '
                  'matches, not committed mutations or predicted savings. Source errors, '
                  'Hide termination and all shared effects must retain their original order.',
    }
    output.write_text(json.dumps(result, indent=2) + '\n')
    print({k: result[k] for k in ('later_scalar_sites', 'input_closed_sites')})


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    inspect(*map(Path, sys.argv[1:]))
