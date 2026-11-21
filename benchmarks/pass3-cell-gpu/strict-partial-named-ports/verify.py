import hashlib,json
from collections import Counter
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/'study.py'));read=lambda p:json.loads(p.read_bytes())
m=read(HERE/'manifest.json')
for k,h in m['sources'].items():assert hashlib.sha256((HERE.parent/k).read_bytes()).hexdigest()==h,k
assert hashlib.sha256((HERE.parent/'explicit-parent-cell-composition/library.json').read_bytes()).hexdigest()==m['donor_library']
links=read(HERE/'signed_commits.json')
for case,r in read(HERE/'results.json').items():
    study['check'](r)
    journal=links[case]
    for mode in study['MODES']:
        q=r[mode];assert len(q['ms'])==len(q['wall_ms'])==4 and median(q['ms'])==q['median_ms']
        seen=set();counts=Counter()
        for i in journal['arms'][mode]:
            child,root,path,ports,run,effects=journal['records'][i]
            assert child not in seen and root!=child;seen.add(child)
            assert len(path)==len(ports)>=1
            for j,(edge,port) in enumerate(zip(path,ports)):
                assert edge[1]==port[1] and port[3]<run
                if j:assert edge[0]==path[j-1][2] and ports[j-1][3]<port[3]
            for k,n in zip(('typed.new','typed.visible','dynamic.new','dynamic.visible','paid.new','paid.visible'),effects):counts[k]+=n
        assert len(seen)==q['counts'].get('source_commits',0)
        assert all(counts.get(k,0)==q['internal_kinds'].get(k,0)for k in set(counts)|set(q['internal_kinds']))
        if mode!='leaf':
            p=q['production_partition'];c=q['production_counts']
            assert p['child_logits_for_audit']==c['audit_score_inputs']==0 and p['production_virtual']==p['signed_children']
    print(case,[(n,r[n]['emitted'][0],r[n]['internal_kinds'].get('typed.visible',0))for n in study['MODES']])
