"""Offline retained-history analysis; does not infer unrecorded winner depths."""
import argparse
import collections
import json
from pathlib import Path


def analyze(history, catalog, program):
    if catalog['recipe'] != program['recipe']['sha256']:
        raise ValueError('Rule metadata does not belong to the history catalog recipe')
    rules = program['recipe']['rules']
    events = history['events']
    sizes = {c['unit']: len(c['source_path']) for c in catalog['completion']['contracts']['implementations']}
    depths, missing, paths = [], [], []
    hist = collections.Counter()
    edges = collections.Counter()
    sets = collections.defaultdict(collections.Counter)
    patterns = collections.Counter()
    cross = collections.Counter()
    joint = collections.Counter()
    repeated = 0
    for i, e in enumerate(events):
        parent = e['parent']
        rule = e['entry'][0]
        group = rules[rule]['metadata']['source_set']
        if parent is None:
            depth, unknown, path = 1, e['truncated_parent'], []
        else:
            if not 0 <= parent < i:
                raise ValueError('Invalid parent ordering')
            depth, unknown = depths[parent] + 1, missing[parent]
            path = paths[parent]
            prev = events[parent]['entry'][0]
            prev_set = rules[prev]['metadata']['source_set']
            edges['same_ruleset' if prev_set == group else 'cross_ruleset'] += 1
            cross[f'{prev_set} -> {group}'] += 1
            patterns[f'{prev}:{e["output"]}->{rule}'] += 1
        repeated += rule in path
        paths.append(path + [rule])
        depths.append(depth)
        missing.append(unknown)
        hist[depth] += 1
        sets[group][depth] += 1
        joint[f'trail={depth},active_cell={sizes[e["unit"]]}'] += 1
    return {
        'scope': 'historical actual Cell runtime training; retained successful events, not all candidates',
        'history_program_sha256': history['program_sha256'],
        'recipe_sha256': catalog['recipe'],
        'depth_definition': 'retained ancestry length, not Cursor.depth; missing ancestry gives a lower bound',
        'events': len(events), 'dropped_events': history['dropped_events'],
        'missing_ancestry_events': sum(missing),
        'run_range': [min(e['run'] for e in events), max(e['run'] for e in events)] if events else [],
        'catalog_limits': catalog['limits'], 'catalog_joins': len(catalog['joins']),
        'retained_depth': dict(sorted(hist.items())),
        'incoming_edges': dict(edges), 'events_repeating_a_rule_in_ancestry': repeated,
        'by_ruleset': {k: dict(sorted(v.items())) for k,v in sorted(sets.items())},
        'trail_vs_active_cell_size': dict(sorted(joint.items())),
        'top_rule_edges': patterns.most_common(12), 'ruleset_edges': cross.most_common(),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('history', 'catalog', 'program', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    report = analyze(*(json.loads(p.read_text()) for p in (args.history, args.catalog, args.program)))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
