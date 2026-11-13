"""Audit generator-produced receipt omission; never transform a runtime Program.

Usage: receipt_omission.py MATERIALIZED_DIR OMIT_DIR ORIGINAL_PROGRAM REPORT
Run after the two documented compiler invocations. This checks the compiled
source delta, not dynamic semantics or memory savings.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def project(core, names):
    result = copy.deepcopy(core)
    declarations = [t for t in result['tables'] if t['name'] in names]
    require({t['name'] for t in declarations} == names, 'missing receipt declaration')
    for t in declarations:
        require(t['kind'] == 'function' and t['merge'] == 'old'
                and t['schema'][-1]['kind'] == 'Unit', 'unexpected receipt declaration')
    result['tables'] = [t for t in result['tables'] if t['name'] not in names]
    writes = 0
    for ruleset in result['rulesets']:
        for rule in ruleset['rules']:
            kept = []
            for effect in rule['head']:
                if effect.get('call', {}).get('table') not in names:
                    kept.append(effect)
                    continue
                require(effect['op'] == 'set' and effect['value'] == {
                    'literal': 0, 'sort': {'name': 'Unit', 'kind': 'Unit'}},
                    'receipt has non-membership effect')
                require(all(set(a) == {'var', 'sort'} for a in effect['args']),
                        'receipt evaluates an expression')
                writes += 1
            rule['head'] = kept
    def check(value):
        if isinstance(value, dict):
            for k, v in value.items():
                check(k)
                check(v)
        elif isinstance(value, list):
            for v in value:
                check(v)
        elif isinstance(value, str):
            require(value not in names, 'remaining receipt reference: ' + value)
    check(result)
    return result, writes


def audit(control, omitted, original):
    load = lambda p: json.loads(p.read_text())
    a, b = load(control / 'program.json'), load(omitted / 'program.json')
    ra, rb = load(control / 'marker-selection.json'), load(omitted / 'marker-selection.json')
    require(a['source_core'] == load(original)['source_core'], 'original source core changed')
    for name in ('source.egg', 'source_sk.egg', 'bake-source.egg'):
        require((control / name).read_bytes() == (omitted / name).read_bytes(), 'source differs: ' + name)
    require(ra['application_receipts_materialized'] is True
            and rb['application_receipts_materialized'] is False, 'wrong generation modes')
    require(rb['receipt_tables'] == [], 'omit still declares receipts')
    for key in ra.keys() | rb.keys():
        if key not in ('receipt_tables', 'application_receipts_materialized'):
            require(ra.get(key) == rb.get(key), 'marker selection changed: ' + key)
    names = set(ra['receipt_tables'])
    require(bool(names), 'empty receipt experiment')
    projected, writes = project(a['source_core'], names)
    require(projected == b['source_core'], 'changes outside generated receipt declarations/writes')
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    return dict(scope='compiled-source delta; not runtime semantic acceptance or memory proof',
                original_core_exact=True, remaining_core_exact=True,
                receipt_tables=sorted(names), removed_write_sites=writes,
                original_sha256=digest(original),
                materialized_sha256=digest(control / 'program.json'),
                omitted_sha256=digest(omitted / 'program.json'))


if __name__ == '__main__':
    control, omitted, original, report = map(Path, sys.argv[1:])
    result = audit(control, omitted, original)
    report.write_text(json.dumps(result, indent=2) + '\n')
    print('receipt-only delta:', len(result['receipt_tables']), 'tables,',
          result['removed_write_sites'], 'writes')
