"""Check native model actions, allocator measurements and complete references without Torch."""
import json
from pathlib import Path
from math import isclose

def check(folder, files=None):
    files=files or {}
    read=lambda n:json.loads(files.get(n,folder/n).read_bytes())
    train=read('train.json')
    assert len(train)==32
    assert {r['family'] for r in train}=={'s0','s1','s2','s3','clamped-ramp','affine-twins','segmented-prefix','window-laplacian'}
    counts={g:[r for r in train if r['group']==g and r['eligible']] for g in ('synthetic','workload')}
    assert [len(counts[g]) for g in counts]==[16,10]
    assert all(r['saved_bytes']<0 for r in counts['synthetic'])
    assert sum(r['saved_bytes']>0 for r in counts['workload'])==2
    policies=read('policies.json')
    test=read('test.json')
    assert set(test)=={'dot-product','fixture','stable-argmax'}
    for name,arms in test.items():
        assert set(arms)==set(policies)|{'keep','compose','natural'}
        assert arms['natural']['domain'][-1]==0
        control=arms['keep']
        oracle=arms['compose']
        assert oracle['saved_bytes']=={'fixture':-224,'dot-product':124,'stable-argmax':96}[name]
        for arm,row in arms.items():
            assert row['graph']==control['graph'] and row['source_sha']==control['source_sha'] and row['runs']==control['runs']
            if arm=='natural':continue
            assert all(row[k]==control[k] for k in ('readers_sha','later_reads','later_unions','source_before','source_after','source_run'))
            assert row['source_before']==row['source_after'] and row['later_reads']>0
            token=row['token']
            assert len(row['token_id'])==64 and len(set(i[1] for i in token['members']))==2
            assert token['members']==control['token']['members'] and token['features']==control['token']['features']
            if arm in policies:
                p=policies[arm]
                assert [p['weights'],p['intercept']]==token['checkpoint']
                z=p['intercept']
                for f,w in zip(token['features'],p['weights']):z+=w*f
                assert isclose(token['score'],z,rel_tol=1e-12,abs_tol=1e-12)
                assert (z>0)==token['compose']
            assert row['saved_bytes']==(oracle['saved_bytes'] if token['compose'] else 0)
            assert row['peak_bytes']==(oracle['peak_bytes'] if token['compose'] else 0)
            assert len(row['retired_owners'])==int(token['compose'])
    fresh=read('fresh.json')
    assert set(fresh)=={'gemm-bias-relu','gated-state'}
    for family,arms in fresh.items():
        assert set(arms)=={'keep','compose','regression','replay','natural'}
        for f in ('runs','graph','source_sha'):assert len({r[f] for r in arms.values()})==1
        for f in ('reads_sha','issued'):assert len({r[f] for k,r in arms.items() if k!='natural'})==1
        for k in ('replay','regression'):
            r=arms[k]
            if r['issued']:
                model=policies[k]
                score=model['intercept']+sum(x*w for x,w in zip(r['x'],model['weights']))
                assert score==r['score'] and (score>0)==r['selected']
                counter=arms['compose' if r['selected'] else 'keep']
                for f in ('members','run','x','later_unions','saved_bytes','peak_bytes'):assert r[f]==counter[f]
    return {**test,**fresh}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('train','test','policies','fresh'):p.add_argument('--'+key,type=Path)
    files={k+'.json':v for k,v in vars(p.parse_args()).items() if v}
    print('Validated paired physical rewards and pre-action model decisions on',len(check(Path(__file__).parent,files)),'native programs.')
