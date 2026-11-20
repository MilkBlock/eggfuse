import hashlib,json,math,sys
from pathlib import Path
from statistics import median
from returns import evaluate
from certify import certificate,lower_request
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    read=lambda f:json.loads((folder/f).read_bytes())
    training=read('training.json');oracle=read('heldout-costs.json')
    assert {e['program'] for e in training}=={'sum-bits','dot-product','jacobi-1d'}
    assert {e['program'] for e in oracle}=={'conjugate-gradient','3mm'}
    weights=read('policies.json')
    assert len(weights)==8
    for e in training+oracle:
        assert len(e['x'])==8 and len(e['original_ns'])==len(e['request_ns'])==(5 if e['program'] in ('sum-bits','dot-product','jacobi-1d') else 3)
        assert min(e['original_ns']+e['request_ns'])>0
    certs=read('certificates.json')
    assert certs=={k:certificate(v['weights']) for k,v in weights.items()}
    for name,c in certs.items():
        spec=dict(connected_requests=[[1,2,0]],wake_roots=4,request_route_gate={'mode':3,'weights':weights[name]['weights']})
        if name.startswith('bandit'):
            assert c['mode']==2 and lower_request(spec)=={'connected_requests':[[1,2,0]],'wake_roots':4}
            diagnostic=dict(spec,audit=True)
            assert lower_request(diagnostic) is diagnostic
        else:assert c['mode'] is None and lower_request(spec) is spec
    # A structural route choosing opposite actions for large and small tables cannot be folded.
    varying={'hidden':[],'bias':[],'output':[1,0,0,0,0,0,0,0],'offset':-1.}
    assert certificate(varying)['mode'] is None
    for p in weights.values():
        w=p['weights'];assert p['params']==sum(map(len,w['hidden']))+len(w['bias'])+len(w['output'])+1 in (9,81)
        assert p['total']==len(training)
    timed=checked(folder,('heldout.json',),('conjugate-gradient','3mm'),raw=False)
    repeat=checked(folder,('seed1709.json',),('conjugate-gradient',),raw=False)
    for data in (timed,repeat):
        for name,arms in data.items():
            assert set(arms)=={'vanilla','off','wake','size-rule','return-0','bandit-0','return-8','bandit-8'}
            for k,r in arms.items():
                if k in ('vanilla','off'):continue
                assert r['route_contexts']==arms['wake']['route_contexts']
                assert r['gate']['choices']==r['route_actions'].count('1')
                assert r['gate']['calls']==len(r['route_actions']) and r['gate']['calls']>0
    assert read('weighted.json')==evaluate(oracle,timed)
    for name,runs in timed.items():
        events=[e for e in oracle if e['program']==name]
        for arm in ('return-0','bandit-0','return-8','bandit-8'):
            w=weights[arm+'-1703']['weights']
            for e,a in zip(events,runs[arm]['route_actions']):
                x=e['x']
                if w['hidden']:
                    x=[math.tanh(sum(i*j for i,j in zip(line,x))+b) for line,b in zip(w['hidden'],w['bias'])]
                z=sum(i*j for i,j in zip(w['output'],x))+w['offset']
                assert abs(z)>1e-6 and (z>0)==(a=='1')
    return timed

if __name__=='__main__':print('Verified paired costs, 8 frozen policies, actual decisions and exact source executions on',len(verify(HERE)),'held-out workloads')
