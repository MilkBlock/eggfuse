"""Expand one saved trace and rank many structural opportunities without rerunning it."""
import argparse
import collections
import json
from pathlib import Path
from analyze import analyze

p = argparse.ArgumentParser(description=__doc__)
for name in ('history', 'catalog', 'program', 'output_dir'):
    p.add_argument(name, type=Path)
a = p.parse_args()
h, c, program = [json.loads(x.read_text()) for x in (a.history, a.catalog, a.program)]
summary = analyze(h, c, program)
events, rules = h['events'], program['recipe']['rules']
chains, children = [], collections.Counter()
patterns = collections.defaultdict(lambda: {'ends': [], 'roots': set(), 'coverage': set()})
for i, event in enumerate(events):
    parent = event['parent']
    chain = ([] if parent is None else chains[parent]) + [i]
    chains.append(chain)
    if parent is not None:
        children[parent] += 1
    for size in range(2, min(6, len(chain)) + 1):
        suffix = chain[-size:]
        key = tuple((None if j == 0 else events[e]['output'], tuple(events[e]['entry'])) for j,e in enumerate(suffix))
        bucket = patterns[key]
        bucket['ends'].append(i)
        bucket['roots'].add(chain[0])
        bucket['coverage'].update(suffix)
ranked = sorted(patterns.items(), key=lambda kv: (-len(kv[1]['coverage']), -len(kv[1]['ends']), repr(kv[0])))
rows = []
for pattern, info in ranked:
    rows.append({'path': pattern, 'occurrences': len(info['ends']),
                 'distinct_retained_roots': len(info['roots']),
                 'unique_events': len(info['coverage']), 'examples': info['ends'][:3]})
summary.update({'pattern_count': len(rows), 'patterns': rows,
                'fork_parent_count': sum(n > 1 for n in children.values()),
                'max_children': max(children.values(), default=0),
                'coverage_note': 'Pattern coverage overlaps; do not add it or treat it as saved work.'})
a.output_dir.mkdir(parents=True, exist_ok=True)
(a.output_dir/'review.json').write_text(json.dumps(summary, indent=2)+'\n')
with (a.output_dir/'trace.txt').open('w') as out:
    out.write('Retained events only; missing ancestry is explicit. This is not Cursor.depth or a winner census.\n')
    for i,e in enumerate(events):
        rid,pivot = e['entry']
        group = rules[rid]['metadata']['source_set']
        unknown = events[chains[i][0]]['truncated_parent']
        out.write(f"event={i} parent={e['parent']} run={e['run']} producer_run={e['producer_run']} set={group} rule={rid} pivot={pivot} output={e['output']} unit={e['unit']} retained_depth={len(chains[i])} missing_ancestry={unknown} children={children[i]} chain={chains[i]} witness={json.dumps(e['witness'])}\n")
    out.write('\nRULE DICTIONARY\n')
    for rid in sorted({e['entry'][0] for e in events}):
        out.write(f"\nRULE {rid} [{rules[rid]['metadata']['source_set']}]\n{rules[rid]['metadata']['name']}\n")
with (a.output_dir/'patterns.txt').open('w') as out:
    out.write('Ranking: distinct retained events covered. Counts overlap and are not savings.\n')
    for row in rows:
        out.write(json.dumps(row)+'\n')
print(json.dumps({'events':len(events),'patterns':len(rows),'fork_parents':summary['fork_parent_count'],
                  'max_children':summary['max_children'],'top':rows[:8]},indent=2))
