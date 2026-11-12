#!/usr/bin/env python3
"""Name typed Entry proofs and attribute existing final rows, not byte savings."""
import collections
import json
import sys
from pathlib import Path

p, proofs, audit = (json.loads(Path(s).read_text()) for s in sys.argv[1:4])
assert p['sha256'] == proofs['program_sha256'] == audit['program_sha256']
assert audit['all_saved_run_checks_equal'] is True
tables = p['recipe']['tables']
assert [t['name'] for t in tables] == sorted(t['name'] for t in tables)
counts = collections.Counter(row['table'] for row in audit['final_state']['rows'])
by = collections.defaultdict(list)
for proof in proofs['exports']:
    by[proof['view']].append(proof)
exports = []
for view, group in by.items():
    table = tables[view]
    coverage = {c for proof in group for c in proof['columns']}
    exports.append(dict(table=table['name'], final_rows=counts[table['name']],
        all_key_columns_covered=coverage == set(range(len(table['schema'])-1)),
        relations=[dict(constructor=tables[pr['constructor']]['name'], columns=pr['columns'],
                        writers=pr['writers']) for pr in group]))
result = dict(scope=proofs['scope'], program_sha256=p['sha256'], exports=exports,
    projections=[dict(x, proof=dict(x['proof'], view_name=tables[x['proof']['view']]['name'],
                 constructor_name=tables[x['proof']['constructor']]['name'])) for x in proofs['projections']],
    limitations=['All-key coverage is a static relation property, not a replacement layout or saved bytes.',
                 'No runtime result alias, receipt or row retirement has been enabled.',
                 'Proofs assume closed source Program; externally inserted View rows require separate validation.'])
Path(sys.argv[4]).write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(dict(relations=sum(len(t['relations']) for t in exports), tables=len(exports),
    final_rows=sum(t['final_rows'] for t in exports),
    fully_covered_rows=sum(t['final_rows'] for t in exports if t['all_key_columns_covered']))))
