import json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent


def verify(folder):
    read=lambda f:json.loads((folder/f).read_bytes())
    groups={**read('results.json'),**read('deriche.json')}
    assert set(groups)=={'sum-bits','conjugate-gradient','3mm','deriche'}
    for case,arms in groups.items():
        types=['original','joint'] if case=='deriche' else ['original','pages','effects','repair','joint']
        assert set(arms)=={'vanilla'}|{provider+'-'+t for provider in ('live','positive') for t in types}
        ref=arms['live-original']
        for k,q in arms.items():
            assert len(q['ms'])==4 and q['median_ms']==median(q['ms'])
            if k=='vanilla':continue
            assert all(q['checks'].values()) and q['aligned'] and 100*q['direct_cells']>=98*q['fresh']
            family,arm=k.split('-')
            assert q['online_root_rhs']==(q['rhs'] if family=='live' else 0)
            assert q['verified_roots']==arms['vanilla']['rhs']
            for f in ('single_winners','multi_winners','cells','state_sha','root_parents','root_ids','nested_ids','rhs','direct_cells'):
                assert q[f]==ref[f]
            for f in ('raw','multi','physical','commits','children'):assert q[f]==arms[family+'-original'][f]
            if arm in ('joint','pages'):
                assert q['words']['audited']>0 and q['block']['completed']>0
            if arm in ('joint','repair'):assert q['repair_work']
            assert len(q['phase_ms'])==4
    ph=read('phases.json')['3mm']
    assert set(ph)=={'live-original','live-joint','positive-original','positive-joint'}
    assert all(len(v)==3 and all(0<s['validation_ms']<s['search']<s['inference'] for s in v) for v in ph.values())
    arena=read('arena.json')
    assert set(arena)=={'3mm','conjugate-gradient'}
    for name,arms in arena.items():
        base=arms['hash-original-live']
        for k,q in arms.items():
            assert len(q['ms'])==4 and median(q['ms'])==q['median_ms']
            if k=='vanilla':continue
            assert all(q['checks'].values()) and q['online_root_rhs']==(q['rhs'] if k.endswith('live') else 0)
            assert q['store']['layout']==k.split('-')[0]
            for f in ('state_sha','cells','single_winners','multi_winners','root_parents','root_ids','nested_ids','rhs','direct_cells'):assert q[f]==base[f]
    return groups

if __name__=='__main__':print('Verified online versus prepaid block execution, original source/physical ledgers and charged phase clocks on',len(verify(HERE)),'programs')
