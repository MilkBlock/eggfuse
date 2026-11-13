"""Join actual physical segments to logical Cell regions; no workload execution."""
import collections
import hashlib
import json
from pathlib import Path
import sys


def census(snapshot):
    source = snapshot['source_storage']
    trace = source['completed_regions']
    if trace['schema'] != 'completed-regions/v1':
        raise ValueError('unsupported physical region trace')
    frames = {f['cell']: f for f in trace['frames']}
    owners = {o['id']: o for o in trace['owners']}
    lifecycle = {f['cell']: f for f in source['fact_lifecycle']['frames']}
    if len(frames) != len(trace['frames']) or len(owners) != len(trace['owners']):
        raise ValueError('duplicate physical identity')
    component_of = {}
    for c in snapshot['ownership_storage']['components']:
        for cell in c['frames']:
            if cell in component_of:
                raise ValueError('duplicate logical source')
            component_of[cell] = c['id']
    by_owner = collections.defaultdict(list)
    by_component = collections.defaultdict(set)
    counts = collections.Counter()
    for cell, frame in frames.items():
        layout = trace['layouts'][frame['layout']]
        state = lifecycle[cell]
        if (not state['completed_storage'] or not state['completed']
                or state['template'] != layout['template']
                or state['started_epoch'] != frame['started_epoch']):
            raise ValueError('source metadata differs')
        ops = {f['op'] for f in state['facts']}
        if len(ops) != len(state['facts']) or not ops.issubset(layout['ops']):
            raise ValueError('source membership differs')
        if frame['owner'] not in owners:
            raise ValueError('missing physical owner')
        by_owner[frame['owner']].append(frame)
        if cell in component_of:
            by_component[component_of[cell]].add(frame['owner'])
        counts['external_source_readers'] += state['retainers'] > 0
    expected = {f['cell'] for f in lifecycle.values() if f['completed_storage']}
    if set(frames) != expected:
        raise ValueError('incomplete completed source inventory')
    patterns = collections.Counter()
    for oid, owner in owners.items():
        members = by_owner[oid]
        if len(members) != owner['sources']:
            raise ValueError('owner source count differs')
        for kind, field in [('slot', 'slots'), ('fact', 'ops')]:
            intervals = sorted((f[kind+'_start'], f[kind+'_start']+len(trace['layouts'][f['layout']][field])) for f in members)
            end = 0
            for start, stop in intervals:
                if start < end or stop > owner[kind+'_entries']:
                    raise ValueError('overlapping or out-of-bounds source ranges')
                end = stop
            occupied = sum(stop-start for start, stop in intervals)
            counts[kind+'_entries_in_source_ranges'] += occupied
            counts[kind+'_entries_outside_source_ranges'] += owner[kind+'_entries']-occupied
        live = sum(len(lifecycle[f['cell']]['facts']) for f in members)
        if live != owner['live_facts']:
            raise ValueError('owner live fact count differs')
        logical = {component_of.get(f['cell']) for f in members}
        counts['physical_owners_spanning_logical_components'] += len(logical) > 1
        counts['sources_in_spanning_owners'] += len(members) if len(logical) > 1 else 0
        counts['owners_without_logical_component'] += None in logical
        # IDs, values, epochs and depth are per-instance obligations, not keys.
        pattern = tuple(sorted((f['layout'], f['slot_start'], f['fact_start']) for f in members))
        patterns[pattern] += 1
    counts.update(completed_sources=len(frames), physical_owners=len(owners),
                  logical_components_with_storage=len(by_component),
                  fragmented_logical_components=sum(len(v)>1 for v in by_component.values()),
                  physical_layout_patterns=len(patterns),
                  owners_in_repeated_patterns=sum(n for n in patterns.values() if n>1),
                  source_positions_in_unique_patterns=sum(map(len, patterns)))
    # Factor only the three existing per-frame layout/range words (24 bytes).
    # Every source still needs an ordinal (8); every owner needs a layout (8).
    # A shared descriptor keeps the old three words at each unique position.
    words = 8
    model = dict(removed_frame_layout_range_bytes=3*words*len(frames),
                 new_source_ordinal_bytes=words*len(frames),
                 shared_position_descriptor_bytes=3*words*sum(map(len, patterns)),
                 owner_layout_handle_bytes=words*len(owners))
    model['payload_delta_bytes'] = (model['removed_frame_layout_range_bytes']
        -sum(model[k] for k in ('new_source_ordinal_bytes', 'shared_position_descriptor_bytes', 'owner_layout_handle_bytes')))
    return dict(counts=dict(counts), header_factorization=model,
                current_source_record_bytes=trace['source_record_bytes'],
                current_owner_record_bytes=trace['owner_record_bytes'])


def analyze(root):
    rows=[]
    for case in ('fact','loopfact','sum-bits','dot-product'):
        path=root/f'{case}.json'; data=path.read_bytes(); snapshot=json.loads(data)
        rows.append(dict(case=case,input_sha256=hashlib.sha256(data).hexdigest(),
                         program=snapshot['program_sha256'],runs=snapshot['runs'],
                         final=snapshot['final_state_sha256'],**census(snapshot)))
    return dict(scope='actual standalone Cell CPU exported segments; offline structural analysis, not a measured representation saving',
                limitations=['Header payload model excludes new registry, allocation headers, padding and capacity.',
                    'Static membership does not prove current values, saturation, visibility or legal RHS skipping.',
                    'Physical regrouping requires separate source-sized movement and external-reader proofs.',
                    'Final ranges do not establish peak memory or lifetime retention costs.'],cases=rows)


if __name__=='__main__':
    Path(sys.argv[2]).write_text(json.dumps(analyze(Path(sys.argv[1])),indent=2)+'\n')
