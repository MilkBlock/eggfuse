"""Mine bounded static child views from saved executions, without runtime claims.

Operator IDs are scoped to each source program. Ports are alpha-renamed, never
canonicalized through current union-find roots. Scalars remain parameters, not
proven equal values. Occurrences retain actual fact identity and lifecycle.
"""
import collections
import itertools
import json
import sys
from pathlib import Path


def signature(nodes):
    ports = {}
    return tuple((operator, tuple(None if p is None else ports.setdefault(p, len(ports))
                                  for p in fields)) for operator, fields in nodes)


def mine(storage, lifecycle):
    metadata = {f['cell']: f for f in lifecycle}
    patterns = collections.defaultdict(list)
    for component in storage['components']:
        shape = storage['shapes'][component['shape']]
        nodes = []
        for ordinal, cell in enumerate(component['frames']):
            frame = metadata.get(cell)
            if frame is None:
                continue
            program = storage['programs'][shape['programs'][ordinal]]
            code = component['frame_codes'][ordinal]
            for fact in frame['facts']:
                op = fact['op']
                fields = program['fields'][op]
                operator = storage['operators'][code][op]
                if not fact['owned'] or fact['hidden'] or not fields or fields[-1] is None or operator == (1 << 64)-1:
                    continue
                ports = tuple(None if p is None else shape['ports'][ordinal][p] for p in fields)
                nodes.append(dict(site=(cell, op), operator=operator, ports=ports,
                                  started=frame['started_epoch'], born=fact['born'], epoch=fact['epoch'],
                                  template=frame['template']))
        # Static output-to-input connections only: no inferred Eq from roots.
        users = collections.defaultdict(list)
        for i, n in enumerate(nodes):
            for p in set(n['ports'][:-1]) - {None}:
                users[p].append(i)
        paths = set()
        for i, n in enumerate(nodes):
            for j in users[n['ports'][-1]]:
                if i == j:
                    continue
                paths.add((i, j))
                for k in users[nodes[j]['ports'][-1]]:
                    if k not in (i, j):
                        paths.add((i, j, k))
        for path in sorted(paths):
            selected = [nodes[i] for i in path]
            key = signature([(n['operator'], n['ports']) for n in selected])
            patterns[key].append(dict(component=component['id'],
                sites=[n['site'] for n in selected], templates=[n['template'] for n in selected],
                crosses_source_frames=len({n['site'][0] for n in selected}) > 1,
                crosses_birth_epochs=len({n['born'] for n in selected}) > 1,
                crosses_start_epochs=len({n['started'] for n in selected}) > 1,
                lifecycle_changed=any(n['born'] != n['epoch'] for n in selected)))
    return patterns


def analyze(root):
    cases = []
    for name in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        data = json.loads((root/name/'candidate-residual-parent-heap.json').read_text())
        patterns = mine(data['ownership_storage'], data['source_storage']['fact_lifecycle']['frames'])
        repeated = [(k, v) for k, v in patterns.items() if len(v) > 1]
        repeated.sort(key=lambda item: (-len(item[0]), -len(item[1]), repr(item[0])))
        used = set()
        selected = []
        # A deterministic greedy packing, not maximum compression or a proof.
        for key, occurrences in repeated:
            accepted = []
            for o in occurrences:
                sites = set(o['sites'])
                if sites.isdisjoint(used):
                    used.update(sites)
                    accepted.append(o)
            selected.append(dict(operations=key, occurrences=len(occurrences),
                disjoint_selected=len(accepted),
                cross_frame=sum(o['crosses_source_frames'] for o in accepted),
                cross_birth_epoch=sum(o['crosses_birth_epochs'] for o in accepted),
                changed_lifecycle=sum(o['lifecycle_changed'] for o in accepted),
                scalar_parameters=sum(p is None for _, fields in key for p in fields),
                example=occurrences[0]))
        cases.append(dict(case=name, source_program=data['program_sha256'],
            repeated_patterns=len(repeated), overlapping_occurrences=sum(len(v) for _, v in repeated),
            disjoint_facts=len(used), disjoint_children=sum(s['disjoint_selected'] for s in selected),
            patterns=selected))
    return dict(scope='saved standalone Cell runtime snapshots; static two/three-operation child-view candidates',
        limitations=['not saturation certificates or authorized RHS skips',
                     'operator identities scoped to source program; no cross-program identity assumed',
                     'scalar parameters and mutable reads require typed compiler validation',
                     'birth epochs are not a proof of source Run order',
                     'greedy disjoint coverage is not byte savings; fact identity is preserved',
                     'linear paths only; branched children are not enumerated'], cases=cases)


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(analyze(Path(sys.argv[1])), indent=2)+'\n')
