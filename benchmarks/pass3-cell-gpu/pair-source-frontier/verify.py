import json
from pathlib import Path
from statistics import median


def verify(folder):
    read=lambda name:json.loads((folder/name).read_bytes())
    data={**read('anchors.json'),**read('transfer.json')}
    assert set(data)=={'sum-bits','dot-product','jacobi-1d','conjugate-gradient','3mm','deriche'}
    for case,arms in data.items():
        baseline=arms['off']
        for name,row in arms.items():
            assert len(row['ms'])==(4 if case in ('3mm','deriche') else 6)
            assert median(row['ms'])==row['median_ms']
            if name=='vanilla':continue
            assert row['aligned'] and all(row['checks'].values()) and row['rhs']==row['neural_rhs']==arms['vanilla']['rhs']
            assert row['direct_cells']*100>=98*row['fresh'] and row['counts']['exhausted']==0
            for f in ('single_winners','multi_winners','root_parents','root_ids','nested_ids','state_sha','cells','direct_cells'):
                assert row[f]==baseline[f],(case,name,f)
            if name!='off':
                assert row['equations']['calls']>0 and row['equations']['numeric_requests']>0
                assert row['counts']['raw_tuples']<baseline['counts']['raw_tuples']
                for f in ('raw','multi','commits','physical','children'):
                    assert row[f]==arms['cached'][f]
        assert arms['indexed']['equations']['index_probes']>0
    repeat=read('seed1709.json');assert set(repeat)=={'sum-bits','dot-product','jacobi-1d'}
    for case,arms in repeat.items():
        for name,v in arms.items():
            assert len(v['ms'])==6 and median(v['ms'])==v['median_ms']
            if name=='vanilla':continue
            assert all(v['checks'].values()) and v['neural_rhs']==v['rhs']==arms['vanilla']['rhs'] and 100*v['direct_cells']>=98*v['fresh']
            for f in ('cells','state_sha','single_winners','multi_winners','root_ids','root_parents','nested_ids'):
                assert v[f]==arms['off'][f]
        assert arms['cached']['counts']['raw_tuples']<arms['off']['counts']['raw_tuples']
        assert arms['indexed']['raw']==arms['cached']['raw']
    profiles=read('profile.json')
    for case,r in profiles.items():
        for w,v in r['by_width'].items():
            assert v['raw']==sum(row['raw'] for row in r['rules'].values() if row['picks']==float(w))
    fixture=read('fixture.json')
    assert fixture['off']['raw']==fixture['unavailable']['raw']==45
    assert fixture['early']['raw']==fixture['indexed']['raw']==6
    assert fixture['early']['equations']['rule_plans']==3 and fixture['early']['equations']['undefined']>0
    assert len({(r['rhs'],r['graph'],r['cells']) for r in fixture.values()})==1
    assert fixture['early']['raw_digest']==fixture['indexed']['raw_digest']
    late=read('union-fixture.json')
    original=late['off']
    assert set(late)=={'off','early','indexed','unavailable'}
    assert late['unavailable']['raw_digest']==original['raw_digest']
    assert late['early']['raw_digest']==late['indexed']['raw_digest']
    for mode,res in late.items():
        for key in ('rhs','graph','cells','marked_winner','winners','source_runs','winner_runs'):
            assert res[key]==original[key],(mode,key)
        assert len(res['marked_winner']['anchors'])==2
        assert res['marked_winner']['run']==3 and {'Int':27} in res['marked_winner']['inputs']
        assert [len(events) for events in res['source_runs']['unions']]==[0,1,0]
        if mode in ('early','indexed'):
            assert res['equations']['rule_plans']==1 and res['equations']['undefined']>0
            assert res['raw']<original['raw']
    return data


if __name__=='__main__':print('Verified derived-port ownership, source conformance and paired medians on',len(verify(Path(__file__).parent)),'programs.')
