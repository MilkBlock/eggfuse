"""Replay component-level boundary routing from saved standalone Cell states.

This is a representation feasibility audit, not execution or a speed estimate.
It reconstructs the existing native-address exclusion and checks every observed
component/root/operator combination against the existing symbolic routes.
"""
import collections
import hashlib
import json
from pathlib import Path
import sys


def census(snapshot):
    storage = snapshot['ownership_storage']
    components = {c['id']: c for c in storage['components']}
    if len(components) != len(storage['components']):
        raise ValueError('duplicate component identity')
    sources = {}
    by_operator = {}
    static_plans = {}
    for cid, c in components.items():
        shape = storage['shapes'][c['shape']]
        if (len(c['frames']) != len(shape['programs'])
                or len(c['frame_codes']) != len(c['frames'])
                or len(c['roots']) != len(shape['signals'])
                or len(c['signals']) != len(c['roots'])):
            raise ValueError('incomplete component wiring')
        for ordinal, source in enumerate(c['frames']):
            if source in sources:
                raise ValueError('source has multiple component positions')
            sources[source] = (cid, ordinal)
        tables = collections.defaultdict(set)
        for symbol, steps in enumerate(shape['signals']):
            for step in steps:
                frame, op = step['frame'], step['op']
                table = storage['operators'][c['frame_codes'][frame]][op]
                if table == (1 << 64) - 1:
                    raise ValueError('signal points to a non-table operation')
                tables[table].add(symbol)
        by_operator[cid] = tables
        static_plans[c['shape'], tuple(c['frame_codes'])] = tables

    def native(cid, symbol, root):
        source, low = root >> 32, root & ((1 << 32) - 1)
        if not low or source not in sources:
            return False
        owner, ordinal = sources[source]
        if owner != cid:
            return False
        c = components[cid]
        shape = storage['shapes'][c['shape']]
        program = storage['programs'][shape['programs'][ordinal]]
        local = program['native'].get(str(low - 1))
        return local is not None and shape['ports'][ordinal][local] == symbol

    groups = collections.defaultdict(set)
    for cid, c in components.items():
        for symbol, root in enumerate(c['roots']):
            if root is not None and not native(cid, symbol, root):
                groups[root, cid].add(symbol)
    count = sum(map(len, groups.values()))
    if count != snapshot['ownership_query_work']['boundary_live']:
        raise ValueError('reconstructed boundary routes differ from runtime counter')
    stats = collections.Counter()
    widths = collections.Counter()
    for (root, cid), original in groups.items():
        c = components[cid]
        widths[len(original)] += 1
        # Enumeration is once per static operator, not weighted by executions.
        for table, candidates in by_operator[cid].items():
            expected = original & candidates
            actual = {symbol for symbol in candidates
                      if c['roots'][symbol] == root and not native(cid, symbol, root)}
            if actual != expected:
                raise ValueError('component projection lost or invented a route')
            stats['operator_cases'] += 1
            stats['static_symbol_checks'] += len(candidates)
            stats['returned_symbol_routes'] += len(actual)
            stats['empty_operator_cases'] += not actual
        stats['unfiltered_symbol_checks'] += len(c['roots'])
    fields = dict(snapshot['graph_fields'])
    return dict(boundary_signals=count, component_root_records=len(groups),
                coalesced_symbol_records=count-len(groups),
                root_component_widths=dict(sorted(widths.items())),
                replay=dict(stats), concrete_static_plans=len(static_plans),
                static_symbol_positions=sum(sum(map(len, p.values())) for p in static_plans.values()),
                old_signal_payload_bytes=16*count,
                proposed_component_id_payload_bytes=4*len(groups),
                graph_boundary_heap_bytes=fields['ownership.boundaries'],
                graph_bytes=snapshot['graph_owned_teardown_bytes'])


def analyze(root):
    cases = []
    for case in ('fact', 'loopfact', 'sum-bits', 'dot-product'):
        path = root/'prefix-all'/case/'source-cell-memory.json'
        data = path.read_bytes()
        snapshot = json.loads(data)
        cases.append(dict(case=case, input_sha256=hashlib.sha256(data).hexdigest(),
                          program_sha256=snapshot['program_sha256'],
                          runs=snapshot['runs'], **census(snapshot)))
    return dict(scope='saved final standalone Cell CPU states; exact boundary membership replay, not measured runtime savings',
                obligations=[
                    'Native ports remain implicit; include them separately in actual query and union dispatch.',
                    'Static plans need concrete operator codes, not port layouts alone.',
                    'Future suffix activation must update the selected static wiring without per-producer consumer lists.',
                    'Union dispatch needs old-root membership or a proven safe superset after root mutation.',
                    'Deletion, query classes, source order, epochs and concurrent read snapshots remain live obligations.',
                    'Payload estimates exclude hash/tree allocation, new plan handles and maintenance; do not subtract them from Graph heap.',
                    'Operator replay is exhaustive on saved groups but is not execution-frequency weighted or a timing result.'
                ], cases=cases)


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(analyze(Path(sys.argv[1])), indent=2)+'\n')
