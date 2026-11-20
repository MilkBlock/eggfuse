import json
from pathlib import Path
from statistics import median


def verify(folder):
    data=json.loads((folder/'results.json').read_bytes())
    assert set(data)=={'sum-bits','dot-product','jacobi-1d','conjugate-gradient'}
    for case,arms in data.items():
        for arm,v in arms.items():
            assert len(v['ms'])==6 and median(v['ms'])==v['median_ms']
            if arm=='vanilla':continue
            assert v['aligned'] and all(v['checks'].values()) and v['rhs']==v['neural_rhs']==arms['vanilla']['rhs']
            assert v['direct_cells']*100>=98*v['fresh'] and v['counts']['exhausted']==0
            for key in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','direct_cells'):
                assert v[key]==arms['one'][key]
            comp='two' if arm in ('primary','columns','both') else 'evidence' if arm=='full' else None
            if comp:
                for f in ('raw','multi','commits','physical','children'):assert v[f]==arms[comp][f]
            assert v['tier']['peak_bytes']<=1<<20
    return data


if __name__=='__main__':print('Verified typed multi-view projections, source endpoints and receipts on',len(verify(Path(__file__).parent)),'programs.')
