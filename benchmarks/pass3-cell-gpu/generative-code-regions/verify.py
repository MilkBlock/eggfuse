"""Verify the stopped transport archive offline. This verifier executes no benchmark."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
for f,h in json.loads((HERE/"manifest.json").read_bytes())["files"].items():
    assert hashlib.sha256((HERE/f).read_bytes()).hexdigest()==h,f
d=json.loads((HERE/'transport.json').read_bytes())
assert d['jobs']=={'2721':'cancelled','2722':'cancelled'}
assert set(d['cases'])=={'sum-bits','3mm'}
for case,arms in d['cases'].items():
    assert set(arms)=={'compound','large_explicit','region','learned'}
    assert len({q['visible_source_origins'] for q in arms.values()})==1
    for name in ('region','learned'):
        r=arms[name]
        assert r['descriptor_wire_bytes']==128*r['regional_or_explicit_descriptors']
        assert r['candidate_pairs_visited']==arms['large_explicit']['candidate_pairs_visited']
    for r in arms.values():assert len(r.get('native_ms',[]))==(4 if case=='sum-bits' else 0)
print('Stopped transport-only archive verified.')
