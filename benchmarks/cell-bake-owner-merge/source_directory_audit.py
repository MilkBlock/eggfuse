"""Join saved source/ownership inventories; observations are not takeover proofs."""
import collections
import hashlib
import json
import pathlib
import sys


def summarize(path):
    raw = path.read_bytes()
    report = json.loads(raw)
    storage = report['source_storage']
    regions = storage['completed_regions']
    frames = {f['cell']: f for f in regions['frames']}
    if len(frames) != len(regions['frames']):
        raise ValueError('duplicate completed source')
    lifecycle = {f['cell']: f for f in storage['fact_lifecycle']['frames']}
    owners = collections.defaultdict(set)
    for source, frame in frames.items():
        if source not in lifecycle or not lifecycle[source]['completed_storage']:
            raise ValueError('completed source missing lifecycle evidence')
        layout = regions['layouts'][frame['layout']]
        if layout['template'] != lifecycle[source]['template']:
            raise ValueError('source layout/template disagreement')
        owners[frame['owner']].add(source)
    for owner in regions['owners']:
        if len(owners[owner['id']]) != owner['sources']:
            raise ValueError('physical owner/source directory disagreement')

    routed = set()
    counts = collections.Counter()
    layouts = collections.defaultdict(set)
    occurrences = collections.Counter()
    epoch_widths = collections.Counter()
    for component in report['ownership_storage']['components']:
        sources = set(component['frames'])
        if len(sources) != len(component['frames']) or sources & routed:
            raise ValueError('source belongs to more than one logical position')
        routed.update(sources)
        if len(component['frame_codes']) != len(component['frames']):
            raise ValueError('missing native source code')
        live = sources & frames.keys()
        physical = {frames[s]['owner'] for s in live}
        epochs = {frames[s]['started_epoch'] for s in live}
        depths = {frames[s]['recipe_depth'] for s in live}
        counts['spans_multiple_physical_owners'] += len(physical) > 1
        counts['physical_owner_has_outside_sources'] += any(owners[o] - sources for o in physical)
        counts['cross_epoch'] += len(epochs) > 1
        counts['cross_recipe_depth'] += len(depths) > 1
        counts['has_routing_only_sources'] += bool(sources - lifecycle.keys())
        epoch_widths[len(epochs)] += 1
        if sources == live:
            key = component['shape'], tuple(component['frame_codes'])
            signature = tuple(frames[s]['layout'] for s in component['frames'])
            layouts[key].add(signature)
            occurrences[key] += 1

    return dict(
        scope='post-execution saved inventory join; not a static proof or memory saving',
        input_sha256=hashlib.sha256(raw).hexdigest(),
        program_sha256=report['program_sha256'],
        completed_sources=len(frames), routed_sources=len(routed),
        sources_in_both_directories=len(frames.keys() & routed),
        completed_without_routing=len(frames.keys() - routed),
        ordinary_sources_with_routing=len((routed & lifecycle.keys()) - frames.keys()),
        routing_only_source_ids=sorted(routed - lifecycle.keys()),
        source_record_bytes=regions['source_record_bytes'],
        source_record_payload=len(frames) * regions['source_record_bytes'],
        source_record_capacity_bytes=regions['source_record_capacity'] * regions['source_record_bytes'],
        ownership_directory_heap=dict(report['graph_fields'])['ownership.frames'],
        components=len(report['ownership_storage']['components']),
        component_obligations=dict(counts), epochs_per_component=dict(epoch_widths),
        fully_present_shape_and_code_groups=len(layouts),
        observed_storage_layout_combinations=sum(map(len, layouts.values())),
        groups_with_multiple_storage_layouts=sum(len(v) > 1 for v in layouts.values()),
        ambiguous_layout_components=sum(occurrences[k] for k, v in layouts.items() if len(v) > 1),
        obligations=[
            'Logical source IDs and FactRef identities remain externally addressable.',
            'Source lifecycle/slice metadata and component routing metadata have distinct responsibilities.',
            'Routing-only sources may still be needed for native Eq addressing.',
            'A logical component is not generally an exclusive physical owner.',
            'Observed equal epochs/layouts do not prove they are invariant for a template.',
        ],
    )


if __name__ == '__main__':
    source, output = map(pathlib.Path, sys.argv[1:])
    output.write_text(json.dumps(summarize(source), indent=2) + '\n')
