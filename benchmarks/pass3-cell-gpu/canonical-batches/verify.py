import json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
def load(n):return json.loads((HERE/n).read_bytes())
roots=load('roots.json');joined=load('frame-forward.json');samples=load('samples.json')
for case,arms in roots.items():
    c=arms['source'];phase=c['work']['phase'];rhs,repair=phase[1:3]
    assert rhs[0]==rhs[6] and rhs[2]==rhs[7]==rhs[8]==0
    assert repair[1]==repair[0]+repair[2] and 0<repair[7]<repair[0]
    assert 0<(repair[2]-(repair[0]-repair[6]))/repair[1]<.025
    for name,v in arms.items():
        assert median(v['ms'])==v['median_ms'] and len(v['ms'])==4
        assert all(w>m for m,w in zip(v['ms'],v['wall']))
        if 'identity'in v:assert v['identity']==c['identity'] and all(v['checks'].values())
    assert c['identity']['neural_rhs']==arms['vanilla']['rhs']
    assert 100*c['identity']['direct_cells']>=98*c['identity']['fresh']
    assert arms['exact']['state']==arms['vanilla']['state']==c['identity']['state_sha']
    d=arms['direct']['work'];m=arms['memo']['work'];b=arms['combined']['work']
    assert d['directory_capacity_bytes']>0 and m['memo_bytes_per_thread']>0 and b['phase'][1][5]>0 and b['phase'][2][3]>0
    assert all(d['phase'][i][1]<phase[i][1] for i in (1,2))
    controls=joined[case];truth=controls['tree']['identity']
    assert truth['per_rhs']==c['identity']['per_rhs_allocations'] and truth['cells']==c['identity']['cells']
    for name,v in controls.items():
        assert len(v['ms'])==len(v['wall'])==4 and v['median_ms']==median(v['ms'])
        if name=='vanilla':continue
        assert all(v['checks'].values()) and v['identity']==truth
        if name in ('tree','compact'):assert len(v['peak_rss_bytes'])==2 and all(n>0 for n in v['peak_rss_bytes'])
        f=v['frame']
        if f['mode']>0:
            assert f['reads'][0]>0 and f['activations']>0
            if f['mode']==1:assert f['reads'][1]==0
        assert sum(v['subscriptions']['forward_histogram'])==v['subscriptions']['native']['dependency_headers']
    sample=samples[case];assert sample['main_thread']==sum(sum(group.values()) for group in sample['scopes'].values())
    assert sum(sample['scopes']['rhs'].values())>20 and sum(sample['scopes']['repair'].values())>20
print('Verified complete source ledgers and allocated Cell identities for every arm, root bounds, active-frame reads and native forward/reverse inventory.')
