import json
from pathlib import Path
from statistics import median


def verify(folder):
    data=json.loads((folder/'results.json').read_bytes())
    assert set(data)=={'sum-bits','dot-product','jacobi-1d','conjugate-gradient'}
    for case,rows in data.items():
        for arm,v in rows.items():
            assert len(v['ms'])==6 and median(v['ms'])==v['median_ms']
            if arm=='vanilla':continue
            assert v['aligned'] and all(v['checks'].values()) and v['neural_rhs']==v['rhs']==rows['vanilla']['rhs']
            assert v['direct_cells']*100>=98*v['fresh']
            for key in ('raw','multi','commits','physical','children','single_winners','multi_winners','cells','root_parents','root_ids','nested_ids'):
                assert v[key]==rows['baseline'][key]
            s=v['prepared']
            assert s['peak_column_bytes'] <= 1<<20
            if arm in ('columns','both'):assert s['coded_values'] and s['reused_values']
            if arm in ('hoist','both'):assert s['hoisted_probes'] and s['index_bindings']
    return data

if __name__=='__main__':print('Verified compiled port reuse, branch participation and all issued/allocated identities on',len(verify(Path(__file__).parent)),'source programs.')
