import hashlib,json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_bytes())
m=read(HERE/'manifest.json')
for key,h in m['sources'].items():assert hashlib.sha256((HERE.parent/key).read_bytes()).hexdigest()==h
assert hashlib.sha256((HERE/'library.json').read_bytes()).hexdigest()==m['library']
lib=read(HERE/'library.json');first={tuple(tuple(e)for e in path)for path in lib['1']['paths']}
assert all((tuple(p[0]),) in first and p[0][2]==p[1][0] for p in lib['2']['paths'])
for case,r in read(HERE/'results.json').items():
    arms=r['arms'];base=arms['leaf']
    assert r['fault']['error']=='strict named return port corruption'
    for n,q in arms.items():
        assert len(q['ms'])==3 and q['median_ms']==median(q['ms']) and all(q['checks'].values())
        assert q['packets']==sum(q['emitted'])+q['selected_children'] and q['yield_per_packet']==q['visible']/q['packets']
        if n=='leaf':continue
        for k in ('checks','commits','physical','root_parents','root_ids','nested_ids','cells','children','single_winners','multi_winners','rhs','state_sha','audit_score','single_ledger','child_decisions','selected_children','birth_digest','end_digest'):
            assert q[k]==base[k],(case,n,k)
        c=q['stats']['counts'];prod=q['production']
        assert prod['no_score_inputs']==prod['source_commits']==c['audit_score_inputs']==c['source_commits']==base['emitted'][0]-q['emitted'][0]
        assert prod['audit_score_inputs']==c['no_score_inputs']==0
        assert prod['direct_spine_lookups']==prod['source_commits'] and q['by_depth'][1][2]==c['two_with_internal_parent']
    print(case,[(n,q['emitted'][0],q['yield_per_packet'])for n,q in arms.items()])
