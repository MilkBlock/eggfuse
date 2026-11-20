"""Check reported scopes, measurements and agreed native endpoint evidence."""
import json
from pathlib import Path
from statistics import median

base=Path(__file__).resolve().parent
sampling=json.loads((base/'samples.json').read_text())
cases=json.loads((base/'results.json').read_text())
profiles=json.loads((base/'tuned-phases.json').read_text())
detailed=json.loads((base/'tuned-production-phases.json').read_text())
for case,study in cases.items():
    proof=study['audit']
    assert proof['rhs']==proof['neural_rhs'] and proof['direct_cells']*100>=98*proof['fresh']
    actual=profiles[case]
    assert actual['state_sha']==proof['state_sha'] and actual['runs']==study['runs']
    assert list(actual['median_ms'].values())==list(map(median,zip(*actual['samples_ms'])))
    assert actual['median_ms']['multi_issue_seal']>actual['median_ms']['multi_frames']>0
    second=detailed[case]
    assert second['state_sha']==proof['state_sha'] and second['runs']==study['runs']
    assert list(second['median_ms'].values())==list(map(median,zip(*second['samples_ms'])))
    assert second['median_ms']['single_verify_attach']>second['median_ms']['single_policy_score']>0
    arms=study['arms']
    archive,production=arms['archive'],arms['production']
    assert production['archived_winners']==0
    assert archive['archived_winners']==archive['single_winners']==production['single_winners']>0
    for name,arm in arms.items():
        assert arm['median_ms']==median(arm['ms']) and len(arm['ms'])==6
        assert all(r>t>0 for r,t in zip(arm['roundtrip_ms'],arm['ms']))
        for phases,total in zip(arm['phase_ms'],arm['ms']):
            assert all(v>=0 for v in phases) and 0.95*total<=sum(phases)<=1.002*total
    for arm in ('vanilla','resident','tuned'):
        sample=sampling[f'{case}-{arm}'];regions=sample['categories']
        assert sample['state_sha']==proof['state_sha']
        assert sum(v for cat in regions.values() for v in cat.values())==sample['main_thread_samples']
        assert sample['main_thread_samples']>1000
        if arm!='vanilla':
            assert regions['execute']['multi_witness'] and regions['execute']['single_generation']
            assert sample['inclusive_scopes']['Store::seal_raw']>0
print('Verified both native endpoint ledgers, charged phases, disabled archive, stack totals and sampler graph digests.')
