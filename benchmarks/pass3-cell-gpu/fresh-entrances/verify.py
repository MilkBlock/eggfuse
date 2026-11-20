"""Verify the sealed ownership and source contracts on the frozen fresh-entry cases."""
import json
from pathlib import Path
from statistics import median

def verify(path):
    rows = json.loads(path.read_bytes())
    assert {key.split('/')[0] for key in rows} == {'sum-bits', 'dot-product', 'jacobi-1d'}
    for key, arms in rows.items():
        assert set(arms) == {'vanilla', 'legacy', 'shared', 'same_width', 'plus_one'}
        baseline = arms['legacy']
        for name, v in arms.items():
            assert v['median_ms'] == median(v['ms']) and len(v['ms']) == 10
            if name == 'vanilla':
                continue
            assert v['aligned'] and all(v['checks'].values())
            assert v['neural_rhs'] == v['rhs'] == arms['vanilla']['rhs']
            assert v['direct_cells'] * 100 >= 98 * v['fresh']
            if name == 'shared':
                for field in ('multi','raw','physical','commits','children','cells'):
                    assert v[field] == baseline[field]
            if name in ('same_width','plus_one'):
                assert v['entrance']['switched'] > 0
        assert arms['plus_one']['entrance']['extra_parent_switches'] > 0
        assert arms['plus_one']['work']['raw_tuples'] < baseline['work']['raw_tuples']
    return rows

if __name__ == '__main__':
    first=verify(Path(__file__).parent/'results.json')
    second=verify(Path(__file__).parent/'second-seed.json')
    assert all(k.endswith('/1703') for k in first) and all(k.endswith('/1709') for k in second)
    print('Verified sealed parent routing, original source schedule, physical attribution and ten timing samples.')
