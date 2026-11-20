from pathlib import Path
import json
from statistics import median

def verify(folder):
    d=json.loads((folder/'results.json').read_bytes())
    assert set(d)=={'sum-bits','dot-product','jacobi-1d','conjugate-gradient'}
    for case,arms in d.items():
        for name,row in arms.items():
            assert len(row['ms'])==6 and median(row['ms'])==row['median_ms']
            if name=='vanilla':continue
            assert row['aligned'] and all(row['checks'].values()) and row['neural_rhs']==row['rhs']==arms['vanilla']['rhs']
            assert row['direct_cells']*100>=98*row['fresh']
            for f in ('raw','commits','physical','multi','children','cells','root_parents','root_ids','single_winners','multi_winners','nested_ids'):
                assert row[f]==arms['forward'][f]
            v=row['domain']
            if name!='forward':assert v['used']>0 and v['rows_after']<v['rows_before'] and v['peak_charge']<=4<<20
    return d

if __name__=='__main__':print('Verified the unchanged raw source stream for every learned root restriction on',len(verify(Path(__file__).parent)),'workloads.')
