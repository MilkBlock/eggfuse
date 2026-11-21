import hashlib
import json
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/'study.py'))
read=lambda p: json.loads(p.read_bytes())
m=read(HERE/'manifest.json')
for shape,h in m['sources'].items():assert hashlib.sha256((HERE.parent/shape).read_bytes()).hexdigest()==h
library=read(HERE/'library.json');prefixes=set()
for k,round in library['rounds'].items():
    ranked={}
    for donor,proof in round['donors'].items():
        for schema,n in proof['suppressed_by_route']:
            key=tuple(tuple(edge)for edge in schema)
            ranked[key]=ranked.get(key,0)+n
            if k=='2':assert (key[0],) in prefixes and key[0][2]==key[1][0]
    selected=sorted(ranked,key=lambda a:(-ranked[a],a))[:library['limit']]
    assert len(selected)<=32 and selected==[tuple(tuple(edge)for edge in schema)for schema in round['selected']]
    assert [ranked[a] for a in selected]==round['credited']
    if k=='1':prefixes.update(selected)
diagnostic=read(HERE/'depth.json')
joint=read(HERE.parent/'integral-filter-joint/results.json')
for name,rows in read(HERE/'results.json').items():
    study['check'](rows)
    base=joint[name]['filter_mixed'];f=rows['full1']
    for k in ('wire_bytes','emitted','root_ids','children','nested_ids','state_sha','rhs'):assert base[k]==f[k],(name,k)
    oracle=diagnostic[name];assert oracle['graph']==f['state_sha'] and oracle['singleton_digest']==f['singleton_digest'] and oracle['native_singleton_depths']==f['native_singleton_depths']
    assert rows['full2']['chain']['attributed'][1]<=int(f['native_singleton_depths']['2'])
    assert rows['baked2']['chain']['attributed'][1]<=oracle['observed_given_donor_prefixes'][1]
    for n in study['MODES']:
        q=rows[n]
        assert len(q['ms'])==len(q['wall_ms'])==4 and median(q['ms'])==q['median_ms']
        assert q['fept']==q['visible']/q['total_packets']
    print(name,[(n,rows[n]['chain']['attributed'],rows[n]['fept'])for n in study['MODES']])
