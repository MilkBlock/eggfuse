import json
from pathlib import Path
from statistics import median
from prepare import CASES,hashfile

def verify(folder):
    d=json.loads((folder/'results.json').read_bytes());m=json.loads((folder/'manifest.json').read_bytes())
    assert set(d)==set(m)==set(CASES)
    suite=folder.resolve().parents[2]/'workloads/pass3'
    for case,arms in d.items():
        source=arms['vanilla'];f=arms['frozen']
        for name,digest in m[case]['parts'].items():assert hashfile(suite/name)==digest
        assert all(f['checks'].values()) and f['aligned'] and f['state_sha']==source['state_sha']
        assert f['neural_rhs']==f['rhs']==source['rhs'] and f['direct_cells']*100>=98*f['fresh']
        for arm in ('vanilla','frozen'):
            v=arms[arm];assert len(v['ms'])==6 and median(v['ms'])==v['median_ms']
    old=d['deriche']['baseline'];assert old['status']=='failed_source_or_attribution' and not old['aligned']
    assert old['differences']['schedule']['index']==818 and 'ms' not in old
    for f in ('single_winners','multi_winners','cells','root_ids','root_parents','nested_ids'):
        assert d['3mm']['baseline'][f]==d['3mm']['frozen'][f]
    return d

if __name__=='__main__':print('Verified two additional original source programs and the explicit failed legacy Deriche arm:',len(verify(Path(__file__).parent)))
