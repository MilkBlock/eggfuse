import json
from pathlib import Path
HERE=Path(__file__).parent
results=json.loads((HERE/'results.json').read_bytes())
assert len(results)==8
for case,r in results.items():
    assert all(r['checks'].values()) and r['neural_rhs']==r['rhs'] and 100*r['direct_cells']>=98*r['fresh']
    c=r['census'];w=c['wire'];d=c['depth'];assert c['tuples']==w['tuples']==sum(c['lcp']) and r['pages']==w['pages']
    assert sum(i*n for i,n in enumerate(c['lcp']))==sum(x['shared'] for x in d)
    assert sum(v['offered'] for v in d)*r['ref_bytes']==w['raw_bytes']
    assert len(d)==c['max_width'] and all(0<=v['repeated_failure']<=min(v['failed'],v['shared_read'])<=v['read']<=v['offered'] for v in d)
    assert all(0<=v['shared_fields']<=v['fields'] for v in d)
    assert w['full_bytes']<=w['first_bytes'] and w['block_full_bytes']<=w['block_first_bytes']
    assert w['encoded_buffer_allocations']==2*w['page_allocation_count']==2*r['pages']
    assert w['field_replay_checks']==4*sum(x['offered'] for x in d)
    assert w['max_seek_tuples']<=32 and w['seek_checks']>=2*r['pages']
print('Verified all eight frozen source trajectories, per-depth counts and backward random-access plus sequential reconstruction of every emitted atom, address and version.')
