#!/usr/bin/env python3
"""Expand v3 handoff layouts and require exact equality with the v2 preparation."""
import argparse
import copy
import json
from pathlib import Path


def compare(before, after):
    assert before['schema'] == 'eggfuse-worker-handoff/v2'
    assert after['schema'] == 'eggfuse-worker-handoff/v3'
    expanded = copy.deepcopy(after)
    layouts = expanded.pop('layouts')
    order = expanded.pop('required_order')
    established = expanded.pop('established_after')
    permission = expanded.pop('worker_execution_proved')
    for rule in expanded['rules']:
        layout = copy.deepcopy(layouts[rule.pop('layout')])
        rule.update(layout)
        rule['required_order'] = order
        rule['established_after'] = established
        for ordinal, effect in enumerate(rule['effects']):
            effect['operation'] = ordinal
            effect['entry_route'] = effect['table']
            effect['worker_execution_proved'] = permission
            kind = effect['kind']
            if kind in ('constructor', 'mutable-read', 'set'):
                address = 'actual-returned-receipt'
            elif kind in ('copy', 'primitive'):
                address = 'local-slot'
            elif kind in ('union', 'hide', 'panic'):
                address = None
            else:
                raise ValueError('unknown effect kind: '+kind)
            effect['result_address'] = address
    original = copy.deepcopy(before)
    for document in (original, expanded):
        document.pop('schema')
        document.pop('sha256')
    assert original == expanded, 'expanded preparation changed'
    size = lambda v: len(json.dumps(v, separators=(',', ':'), ensure_ascii=False).encode())
    return dict(scope='compiler handoff artifact only; no executor changes or timing',
                program=before['program'], before_bytes=size(before), after_bytes=size(after),
                reduction=1-size(after)/size(before), rules=len(after['rules']),
                layouts=len(layouts), exact_expansion=True,
                forecast_unchanged=before['completion_forecast']==after['completion_forecast'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'after', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
    args.output.write_text(json.dumps(result, indent=2)+'\n')
