import json
from statistics import median
from pathlib import Path
HERE=Path(__file__).resolve().parent


def verify(folder):
    data=json.loads((folder/'results.json').read_bytes());rss=json.loads((folder/'rss.json').read_bytes())
    assert set(data)=={'sum-bits','conjugate-gradient','3mm'} and set(rss)=={'conjugate-gradient','3mm'}
    hashes=json.loads((folder/'identities.json').read_bytes());assert len(set(hashes.values()))==4
    for name,arms in data.items():
        assert set(arms)=={'vanilla','hash','arena','page16','page64','hash-exact','arena-exact','page16-exact','page64-exact'}
        for mode,v in arms.items():
            assert len(v['ms'])==4 and median(v['ms'])==v['median_ms']
            if mode=='vanilla':continue
            ref=arms['hash'];s=v['store']
            assert v['state_sha']==ref['state_sha'] and all(v['checks'].values())
            assert s['live']==ref['store']['live'] and s['record_capacity']>=s['live']
            assert len(v['phases'])==4 and all(len(row)==5 and min(row)>=0 for row in v['phases'])
            if mode.endswith('-exact'):continue
            assert v['neural_rhs']==v['rhs']==arms['vanilla']['rhs'] and v['direct_cells']*100>=98*v['fresh']
            for k in ('raw','multi','physical','cells','single_winners','multi_winners','root_parents','root_ids','nested_ids','direct_cells'):
                assert v[k]==ref[k]
            if mode.startswith('page'):
                assert s['width']==int(mode[4:]) and len(s['histogram'])==s['width']+1
                assert sum(s['histogram'])==s['primary']+s['outliers']
                assert sum(i*n for i,n in enumerate(s['histogram']))==s['live']==s['inserted']-s['removed']
        if name in rss:
            assert set(rss[name])==set(hashes)
            for v in rss[name].values():assert len(v['samples'])==3 and v['median']==median(v['samples'])
    return data

if __name__=='__main__':print('Verified stable Cell ids, ordered source effects, physical occupancy and paired timings on',len(verify(HERE)),'programs')
