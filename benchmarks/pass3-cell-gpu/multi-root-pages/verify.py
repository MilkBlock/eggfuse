"""Validate measured page controls, direct physical coverage and strictly rejected faults."""
import json
from pathlib import Path
from statistics import median

values=json.loads((Path(__file__).with_name('results.json')).read_text())
for case,result in values.items():
    proof=result['evidence']
    assert all(proof['checks'].values())
    assert proof['rhs']==proof['neural_rhs'] and 100*proof['direct_cells']>=98*proof['fresh']
    assert 0<result['pages']<result['raw_tuples']
    assert set(result['negative_controls'])=={'1','2','3'}
    assert all(n>0 and 'no verified root recipe' in error for n,error in result['negative_controls'].values())
    assert all(len(ms)==6 and median(ms)==result['median_ms'][arm] for arm,ms in result['ms'].items())
    for arm,ms in result['ms'].items():
        assert all(t<r for t,r in zip(ms,result['roundtrip_ms'][arm]))
print('Verified source-equivalent page and separate requests, full direct coverage ledger, three rejected faults and timings.')
