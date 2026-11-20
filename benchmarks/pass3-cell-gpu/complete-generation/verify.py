import json
from pathlib import Path
from statistics import median

def verify(folder):
    d=json.loads((folder/'results.json').read_bytes())
    assert set(d)=={'sum-bits','deriche'}
    for case,arms in d.items():
        assert set(arms)=={'bounded','complete','paged','frozen','vanilla'}
        failed=arms['bounded']
        assert 'unexplored branch' in failed['source_error'] and 'state_sha' not in failed
        for arm in ('vanilla','complete','paged','frozen'):
            v=arms[arm]
            assert len(v['ms'])==4 and median(v['ms'])==v['median_ms']
            if arm=='vanilla':continue
            assert v['aligned'] and all(v['checks'].values()) and v['rhs']==v['neural_rhs']==arms['vanilla']['rhs']
            assert 100*v['direct_cells']>=98*v['fresh']
            for key in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','state_sha','cells','rhs','direct_cells'):
                assert v[key]==arms['complete'][key]
        for k in ('raw','physical','multi','commits','children','raw_packets'):
            assert arms['complete'][k]==arms['paged'][k]
        lim=8192 if case=='deriche' else 7
        assert arms['paged']['max_page']==lim and arms['complete']['max_page']>lim and arms['paged']['page_count']>arms['complete']['page_count']
    assert d['deriche']['bounded']['runs']==818 and 'rule 249' in d['deriche']['bounded']['source_error']
    assert d['deriche']['complete']['rhs']==635818
    assert d['sum-bits']['bounded']['legacy_limit_rejected']
    cli=json.loads((folder/'bundle-contract.json').read_bytes())
    assert cli['complete']['rhs']==cli['complete']['neural_rhs']==d['sum-bits']['complete']['rhs']
    assert cli['bounded_ok']==cli['complete'] and cli['invalid']=={'rejected':True}
    for k in ('bounded','old'):
        assert cli[k]['unfinished_generation']==dict(run=9,rule=279,limit=2,attempts=2,reason='unexplored_parent_branch')
    edge=json.loads((folder/'edge.json').read_bytes())
    assert edge['one']['reached_limit']==edge['one']['complete_rhs']==edge['one']['tuples']==1
    assert edge['two']['complete_rhs']==edge['two']['tuples']==2 and edge['two']['unfinished']['limit']==1
    old=cli['old_archive_control'];assert old==dict(archive_off=4588,archive_on=7265,rhs=7265,same_state=True)
    rss=json.loads((folder/'footprint.json').read_bytes())
    for case,arms in rss.items():
        for v in arms.values():assert len(v['rss'])==3 and median(v['rss'])==v['median_rss']
    return d

if __name__=='__main__':print('Verified explicit bounded failure, complete frozen bundles and fully sealed page equivalence:',len(verify(Path(__file__).parent)),'source programs.')
