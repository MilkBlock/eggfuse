"""Check that every positive RHS treatment preserves ordered effects and physical source allocation."""
import json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
def load(name):return json.loads((HERE/name).read_bytes())
construct=load('constructor-results.json');grouped=load('projection-results.json');wall=load('wall.json')
for case,arms in construct.items():
    for study in (arms,grouped[case]):
        for name,arm in study.items():
            assert len(arm['ms'])==6 and median(arm['ms'])==arm['median_ms']
            if name=='vanilla':continue
            assert all(arm['checks'].values()) and arm['state']==arms['neural-off']['state']
            assert all(len(row)==5 and sum(row)<=1.01*total for row,total in zip(arm['phases'],arm['ms']))
    for prefix,variants in [('neural',('nullary','full')),('exact',('full',))]:
        plain=arms[prefix+'-off']
        for variant in variants:
            guarded=arms[prefix+'-'+variant]
            assert plain['physical']==guarded['physical']
            for k in ('cells','constructor_requests','constructor_reused'):
                assert plain['cache'][k]==guarded['cache'][k]
            samples=guarded['cache']['eligible_hits_keymiss_stampmiss']
            assert samples[0]>=samples[1]>0 and guarded['cache']['verified']
    original,fast=(grouped[case][k] for k in ('neural-off','neural-grouped'))
    assert original['physical']==fast['physical']==arms['neural-off']['physical']
    q=fast['projection']
    assert q['whole_projections']==q['whole_commits']==q['applied']==arms['vanilla']['rhs']
    assert q['root_header_checks']<original['projection']['root_header_checks']
    assert 'changed across source commit' in fast['rejected_missing_slot'][1]
    for sample in wall[case].values():
        assert len(sample['wall_ms'])==4 and all(t>w>0 for t,w in zip(sample['wall_ms'],sample['execute_ms']))
print('Verified all four source ledgers, exact hit-by-hit row checks, all direct root projections, physical allocation identities and corrupted-root rejections.')
