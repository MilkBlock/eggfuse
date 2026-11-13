"""Lower observed child patterns to typed, zero-copy candidate views.

This is offline compiler input preparation, not runtime admission. Views refer to
existing fact sites. They never materialize a second set of facts or bindings.
"""
import collections
import json
import sys
from pathlib import Path
from subcell_patterns import mine


def compile_layout(pattern, tables):
    slots = {}
    slot_ids = {}
    operations = []
    for operation, (operator, ports) in enumerate(pattern):
        if not 0 <= operator < len(tables):
            return None, 'unknown_operator'
        table = tables[operator]
        if table['kind'] != 'constructor':
            return None, 'mutable_or_relation'
        if len(ports) != len(table['schema']):
            return None, 'arity'
        columns = []
        for column, (port, sort) in enumerate(zip(ports, table['schema'])):
            if (port is None) == (sort.get('kind') == 'eq'):
                return None, 'column_sort_mismatch'
            key = ('field', operation, column) if port is None else ('eq', port)
            encoded_sort = json.dumps(sort, sort_keys=True, separators=(',', ':'))
            if key in slots and slots[key] != encoded_sort:
                return None, 'port_sort_conflict'
            slots[key] = encoded_sort
            columns.append(slot_ids.setdefault(key, len(slot_ids)))
        operations.append(dict(table=table['name'], schema=table['schema'], columns=columns))
    # All ports remain exported until a consumer/lifetime analysis proves a
    # smaller interface. Table names+schemas, not program-local IDs, pool layouts.
    return dict(operations=operations, ports=[dict(slot=p, sort=json.loads(s))
                for p, s in sorted((slot_ids[k], s) for k, s in slots.items())]), None


def project(storage, sites):
    locations = {cell: (c, ordinal) for c in storage['components']
                 for ordinal, cell in enumerate(c['frames'])}
    projection = {}
    result = []
    for cell, op in sites:
        c, ordinal = locations[cell]
        shape = storage['shapes'][c['shape']]
        fields = storage['programs'][shape['programs'][ordinal]]['fields'][op]
        columns = []
        for local in fields:
            key = ('field', cell, op, len(columns)) if local is None else ('eq', c['id'], shape['ports'][ordinal][local])
            columns.append(projection.setdefault(key, len(projection)))
        result.append(columns)
    return result, [dict(component=key[1], symbol=key[2]) if key[0] == 'eq'
                    else dict(fact=[key[1], key[2]], column=key[3]) for key in projection]


def learn(root):
    layouts, layout_ids, cases = [], {}, []
    for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        directory = root/name
        heap = json.loads((directory/'candidate-residual-parent-heap.json').read_text())
        program = json.loads((directory/'candidate.json').read_text())
        if heap['program_sha256'] != program['sha256']:
            raise ValueError('snapshot/source identity mismatch')
        storage = heap['ownership_storage']
        patterns = mine(storage, heap['source_storage']['fact_lifecycle']['frames'])
        rejected = collections.Counter()
        admitted = []
        for pattern, occurrences in patterns.items():
            if len(occurrences) < 2:
                continue
            layout, reason = compile_layout(pattern, program['recipe']['tables'])
            if reason:
                rejected[reason] += len(occurrences)
                continue
            admitted.append((pattern, layout, occurrences))
        admitted.sort(key=lambda p: (-len(p[0]), -len(p[2]), repr(p[0])))
        used, views = set(), []
        for pattern, layout, occurrences in admitted:
            for occurrence in occurrences:
                if not set(occurrence['sites']).isdisjoint(used):
                    continue
                columns, ports = project(storage, occurrence['sites'])
                if columns != [op['columns'] for op in layout['operations']]:
                    raise ValueError('observed view does not implement typed layout')
                key = json.dumps(layout, sort_keys=True, separators=(',', ':'))
                if key not in layout_ids:
                    layout_ids[key] = len(layouts)
                    layouts.append(layout)
                used.update(occurrence['sites'])
                views.append(dict(layout=layout_ids[key], facts=occurrence['sites'], ports=ports,
                    crosses_birth_epochs=occurrence['crosses_birth_epochs'],
                    lifecycle_changed=occurrence['lifecycle_changed']))
        cases.append(dict(case=name, source_program=program['sha256'],
                          rejected_overlapping_occurrences=dict(rejected),
                          selected_facts=len(used), views=views))
    return dict(schema='eggfuse-observed-child-views/v1', layouts=layouts, cases=cases,
        obligations=['successful Entry and delta ownership', 'current fact identity and visibility',
                     'original Run/effect ordering', 'generation and retirement',
                     'external users of exported ports'],
        executable=False)


def summary(plan):
    return dict(scope='offline typed child-view compilation from standalone Cell snapshots; no runtime takeover',
        layouts=len(plan['layouts']), cases=[dict(case=c['case'], views=len(c['views']),
            selected_facts=c['selected_facts'], layouts=len({v['layout'] for v in c['views']}),
            cross_birth_epoch=sum(v['crosses_birth_epochs'] for v in c['views']),
            rejected_overlapping_occurrences=c['rejected_overlapping_occurrences']) for c in plan['cases']],
        obligations=plan['obligations'])


if __name__ == '__main__':
    plan = learn(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(plan, indent=2)+'\n')
    Path(sys.argv[3]).write_text(json.dumps(summary(plan), indent=2)+'\n')
