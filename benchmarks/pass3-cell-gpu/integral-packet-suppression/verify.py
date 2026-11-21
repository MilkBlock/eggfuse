"""Verify real wire savings and constructor identity attribution from saved receipts."""
import hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
read=lambda name:json.loads((D/name).read_bytes())
for f,sha in read('manifest.json')['sources'].items():assert hashlib.sha256((D.parent/f).read_bytes()).hexdigest()==sha
for case,r in read('results.json').items():
    base,on=r['external'],r['closed'];c=on['internal']['counts']
    assert all(base[k]==on[k] for k in ('checks','single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','rhs','direct_cells','children','multi','state_sha','scores','births','survivors','birth_trace','end_trace','commits','physical','merge_decisions','merge_selected'))
    assert all(base['checks'].values()) and all(on['checks'].values())
    assert base['emitted'][0]-on['emitted'][0]==c['closed_lanes']==c['confirmed']==c['original_checks']>0
    assert base['emitted'][1]==on['emitted'][1] and base['wire_bytes']>on['wire_bytes']
    assert c['nonempty_banks']==sum(c[k] for k in ('closed_banks','without_offer','cardinality','order_version','uncertified'))
    assert r['fault']['error']=='integral release epoch or watermark mismatch'
    e=read('effective.json')[case]
    for k,q in e.items():
        assert q['owned_births']+q['other_births']==r[k]['births'] and q['owned_visible']+q['other_visible']==r[k]['survivors']
        assert q['root_and_selected_child']==sum(q['issued'])+q['selected_child']
        assert q['owned_visible']/q['root_and_selected_child']==q['visible_per_packet']
    print(case,c['closed_banks'],c['closed_lanes'],e['external']['visible_per_packet'],e['closed']['visible_per_packet'])
