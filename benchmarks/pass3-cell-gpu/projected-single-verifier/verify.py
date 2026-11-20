import json
from pathlib import Path
from statistics import median

def verify(path):
    data=json.loads(path.read_bytes())
    assert set(data)=={'sum-bits','dot-product','jacobi-1d','conjugate-gradient'}
    for case,arms in data.items():
        assert set(arms)=={'vanilla','off','forward','projection','canonical'}
        for name,v in arms.items():
            assert len(v['ms'])==6 and median(v['ms'])==v['median_ms']
            if name=='vanilla':continue
            assert all(v['checks'].values()) and v['aligned'] and v['rhs']==v['neural_rhs']==arms['vanilla']['rhs']
            assert v['direct_cells']*100>=98*v['fresh']
            for field in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','cells'):
                assert v[field]==arms['off'][field]
            if name in ('projection','canonical'):
                for f in ('raw','multi','commits','physical','children','single_work'):assert v[f]==arms['forward'][f]
                assert v['projection']['programs'] and v['projection']['attempts'] and v['projection']['successes']
        assert arms['canonical']['projection']['canonical_key_proofs']>0
    return data

if __name__=='__main__':print('Verified compiled query fields and full native receipts:',len(verify(Path(__file__).with_name('results.json'))),'workloads')
