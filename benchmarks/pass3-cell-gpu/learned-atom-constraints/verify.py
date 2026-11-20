import json
from pathlib import Path
from statistics import median


def verify(folder):
    data=json.loads((folder/'results.json').read_bytes())
    assert set(data)=={'sum-bits','dot-product','jacobi-1d','conjugate-gradient'}
    for case,arms in data.items():
        assert set(arms)=={'vanilla','one','local','cached','two','two-cached','three','three-cached'}
        for arm,v in arms.items():
            assert median(v['ms'])==v['median_ms'] and len(v['ms'])==6
            if arm=='vanilla':continue
            assert v['aligned'] and all(v['checks'].values()) and v['neural_rhs']==arms['vanilla']['rhs']==v['rhs']
            assert 100*v['direct_cells']>=98*v['fresh'] and not v['counts']['exhausted']
            for f in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','cells','direct_cells'):
                assert v[f]==arms['one'][f],(case,arm,f)
            s=v['atom']
            assert sum(s[f] for f in ('failure_literal','failure_local','failure_cross','failure_header'))==v['counts']['raw_parent_rejects']
        for f in ('raw','multi','commits','physical','children'):assert arms['local'][f]==arms['cached'][f]
    return data


if __name__=='__main__':print('Verified source equivalence and classification of every failed sealed tuple on',len(verify(Path(__file__).parent)),'programs.')
