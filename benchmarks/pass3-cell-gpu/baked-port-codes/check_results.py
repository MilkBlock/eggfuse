"""Recheck the actual certificate and physical identities within each checkpoint family."""
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
ANCHORS = {'sum-bits', 'dot-product', 'jacobi-1d'}


def check(filename, families, cases, seeds, formats):
    runs = json.loads((HERE / filename).read_bytes())
    assert set(runs) == {f'{case}/{seed}' for case in cases for seed in seeds}
    for workload, result in runs.items():
        vanilla = result['vanilla']
        for family in families:
            base = result[f'{family}-weights']
            offline = result['offline_compile'][family]
            assert offline['bytes'] == 72 + 4 * 65536 and len(offline['hash']) == 64
            for impl in formats:
                arm = result[f'{family}-{impl}']
                assert arm['aligned'] and all(arm['checks'].values())
                assert arm['rhs'] == arm['neural_rhs'] == vanilla['rhs']
                assert arm['direct_cells'] * 100 >= 98 * arm['fresh']
                for key in ('state_sha', 'raw', 'emitted', 'physical', 'commits', 'multi', 'children', 'cells'):
                    assert arm[key] == base[key], (workload, family, impl, key)
                assert len(arm['ms']) == len(vanilla['ms']) >= 6
                assert arm['median_ms'] == median(arm['ms'])
    return runs


if __name__ == '__main__':
    lookup = check('lookup-results.json', ('three', 'tied'), ANCHORS, (1703, 1709),
                   ('weights', 'table', 'column'))
    assert lookup['sum-bits/1703']['corruption_rejected'] == {'weights': True, 'table': True}
    check('packed-results.json', ('tied',), ANCHORS | {'conjugate-gradient'}, (1703,),
          ('weights', 'table', 'packed'))
    print('Verified ten workload/seed batches, sealed proposals, all source events, and actual Cell IDs.')
