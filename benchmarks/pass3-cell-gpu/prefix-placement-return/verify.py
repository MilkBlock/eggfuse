"""Check causal pair identity, native policy decisions and held-out whole-trajectory rewards."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
CASES=('dot-product','stable-argmax','gemm-bias-relu','gated-state')


def verify(folder):
    read=lambda name:json.loads((folder/name).read_bytes())
    prior=json.loads((HERE.parent/'prospective-owner-placement/stream.json').read_bytes())
    costs={}
    for name in CASES:
        data=read(name+'-episodes.json');ref=data['reference'];rows=data['episodes']
        expected=prior[name]['pooled/keep']
        assert data['sham_identical'] and data['sham']['source']==ref['source']==expected['source_sha']
        assert data['sham']['graph']==ref['graph']==expected['graph'] and ref['runs']==expected['runs']
        assert ref['selected']==0 and ref['count']>len(rows)>0
        assert len({r['id'] for r in rows})==len(rows)
        for e in rows:
            a,b=e['outcomes'];N=len(e['members'])
            assert N==len(set(e['members']))==e['x'][0] and e['source_ports']
            assert len(e['x'])==8 and len(e['port_digest'])==64
            assert e['port_runs']==ref['runs']-e['run']+1
            assert e['private_owner'][1]==N<=e['old_owner'][1]
            assert a['pre_owner_byte_runs']==b['pre_owner_byte_runs']
            assert e['terminal_saving']==a['terminal_graph_bytes']-b['terminal_graph_bytes']
            assert e['owner_area_saving']==a['owner_byte_runs']-b['owner_byte_runs']
            assert b['placement'][0]==1 and a['placement'][0]==0
            for v in (a,b):
                assert v['physical']['focus_backing_max']>=N and v['owner_peak']>=v['terminal_owner_charge'][6]
        costs[name]=rows
    policies=read('policies.json');runs=read('deployment.json')
    for line in (folder/'support.jsonl').read_text().splitlines():
        name,arm,support=json.loads(line)
        assert 'feature_support' not in runs[name][arm]
        runs[name][arm]['feature_support']=support
    assert set(policies)=={'birth_saving','terminal_saving','owner_area_saving'}
    assert set(runs)==set(CASES[2:])
    for k,p in policies.items():
        assert tuple(p['donors'])==CASES[:2] and p['examples']==sum(len(costs[n]) for n in CASES[:2])
        assert len(p['weights'])==9 and p['unit']>=1
    for name,arms in runs.items():
        assert set(arms)=={'pool','private','multiple',*policies}
        for arm,r in arms.items():
            w=([1.]+[0.]*7+[-1.5] if arm=='multiple' else policies.get(arm,{'weights':[0]*8+[int(arm=='private')]})['weights'])
            chosen=[e for e in costs[name] if w[-1]+sum(a*b for a,b in zip(w,e['x']))>0]
            assert r['source']==prior[name]['pooled/keep']['source_sha'] and r['graph']==prior[name]['pooled/keep']['graph']
            assert sum(n for _,n,_ in r['feature_support'])==r['offers']
            assert sum(n*chosen for _,n,chosen in r['feature_support'])==r['selected']
            assert all((w[-1]+sum(a*b for a,b in zip(w,x))>0)==chosen for x,_,chosen in r['feature_support'])
            assert 0<=r['selected']<=r['offers']
            assert r['graph_saving']==r['paired_terminal_bytes']-r['terminal_graph_bytes']
            assert r['area_saving']==r['paired_byte_runs']-r['owner_byte_runs']
            assert r['episode_selected']==len(chosen)
            assert r['isolated_graph_delta']==sum(e['terminal_saving'] for e in chosen)
            assert r['isolated_area_delta']==sum(e['owner_area_saving'] for e in chosen)
        assert arms['pool']['graph_saving']==arms['pool']['selected']==arms['pool']['area_saving']==0
        assert arms['private']['selected']==arms['private']['offers']
    curves=read('curves.json')
    assert set(curves)==set(CASES[2:])
    for name,r in curves.items():
        a,b=r['dynamic_curves']
        assert len(a)==len(b)==r['post_action_runs']==runs[name]['pool']['runs']-r['run']+1
        assert r['graph_byte_runs_saving']==sum(a)-sum(b)
        assert r['terminal_saving']==a[-1]-b[-1] and r['static_program_bytes']>0
        assert r['source']==runs[name]['pool']['source'] and r['graph']==runs[name]['pool']['graph']
    timing=read('timing.json')
    for name,arms in timing.items():
        assert name in CASES[2:] and set(arms)=={'stock','score-pool','terminal_saving','owner_area_saving'}
        for k,r in arms.items():
            assert len(r['ms'])==len(r['maintenance_ms'])==4
            assert all(0<b<a for a,b in zip(r['ms'],r['maintenance_ms']))
            assert r['median_ms']==sorted(r['ms'])[1]/2+sorted(r['ms'])[2]/2
            if k!='stock':assert all(0<=s<=n for n,s in r['choices'])
    return costs


if __name__=='__main__':
    print('Verified single-prefix forked counterfactuals and held-out native placement in',len(verify(HERE)),'programs')
