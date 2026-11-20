import json
from pathlib import Path
from statistics import median


def verify(folder):
    data={}
    for filename in ('anchors.json','large.json'):
        data.update(json.loads((folder/filename).read_bytes()))
    assert set(data)=={'sum-bits','dot-product','jacobi-1d','conjugate-gradient'}
    for case,arms in data.items():
        source,off=arms['vanilla'],arms['off']
        for name,row in arms.items():
            assert len(row['ms'])==6 and median(row['ms'])==row['median_ms']
            if name=='vanilla':continue
            assert row['aligned'] and all(row['checks'].values()) and row['rhs']==row['neural_rhs']==source['rhs']
            assert row['direct_cells']*100>=98*row['fresh'] and row['counts']['exhausted']==0
            for field in ('state_sha','cells','single_winners','multi_winners','root_parents','root_ids','nested_ids'):
                assert row[field]==off[field], (case,name,field)
            p=row['guards']
            assert p['peak_bytes']<=4<<20
            if name!='off':
                assert p['probes'] and p['index_rows'] and row['raw_packets']<=off['raw_packets']
        assert arms['both2']['guards']['rejected_old'] and arms['both2']['guards']['rejected_absent']
    assert data['sum-bits']['off']['invalid_control'] and data['conjugate-gradient']['off']['invalid_control']
    return data


if __name__=='__main__':
    print('Verified full source order, learned winners, physical receipts and invalid-control streams on',len(verify(Path(__file__).parent)),'native programs.')
