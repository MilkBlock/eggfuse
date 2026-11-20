"""Common offline check for ablations that preserve complete raw neural issuance."""
import json
from pathlib import Path
from statistics import median


def checked(folder,archives,expected_cases,raw=True):
    data={}
    for filename in archives:
        batch=json.loads((folder/filename).read_bytes())
        assert not data.keys()&batch.keys()
        data.update(batch)
    assert set(data)==set(expected_cases)
    for case,arms in data.items():
        ref=arms.get('off',arms.get('source'));assert ref
        for arm,v in arms.items():
            assert len(v['ms'])>=4 and median(v['ms'])==v['median_ms']
            if arm=='vanilla':continue
            assert v['aligned'] and all(v['checks'].values()) and v['neural_rhs']==v['rhs']==arms['vanilla']['rhs']
            assert 100*v['direct_cells']>=98*v['fresh'] and v.get('counts',{}).get('exhausted',0)==0
            keys=['single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','state_sha']
            if raw:keys.extend(['raw','physical','commits','multi','children'])
            for key in keys:assert v[key]==ref[key],(case,arm,key)
    return data


CASES=('sum-bits','dot-product','jacobi-1d','conjugate-gradient','3mm','deriche')
