import json
from pathlib import Path
from statistics import median

def verify(folder):
    read=lambda s:json.loads((folder/(s+'.json')).read_bytes())
    pairs=read('training-pairs');models=read('training');data=read('results')
    assert set(pairs)=={'affine-twins','clamped-ramp','segmented-prefix','window-laplacian'}
    assert set(data)=={'sum-bits','dot-product','jacobi-1d','conjugate-gradient'} and set(pairs).isdisjoint(data)
    counts={}
    for v in pairs.values():
        assert sum(n for _,_,n in v['pairs'])+v['alias']+v['omitted']==v['failures']
        for left,right,n in v['pairs']:
            assert 0<=left<right<65536 and n>0
            counts[left,right]=counts.get((left,right),0)+n
    for head,config in models.items():
        weights=read(head)
        assert weights['q']==weights['k'] and weights['bits']==config['bits'] and len(weights['q'])==10
        assert all(len(row)==16 for row in weights['q'])
        assert all(not any(row) for row in weights['q'][weights['bits']:])
        assert config['unique_pairs']==len(counts) and config['paired_events']==sum(counts.values())
    for case,arms in data.items():
        for name,v in arms.items():
            assert median(v['ms'])==v['median_ms'] and len(v['ms'])==6
            if name=='vanilla':continue
            assert v['aligned'] and all(v['checks'].values()) and v['rhs']==v['neural_rhs']==arms['vanilla']['rhs']
            assert v['direct_cells']*100>=98*v['fresh'] and v['counts']['exhausted']==0
            for k in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','cells'):
                assert v[k]==arms['one'][k]
    return data

if __name__=='__main__':print('Verified native training rejects, frozen heads and complete source execution on',len(verify(Path(__file__).parent)),'new programs.')
