"""Verify coverage and attribution for the independent multi-witness scope."""
import json
from pathlib import Path

def check(root):
    d=root/'results';read=lambda n:json.loads((d/n).read_bytes())
    a,b,replay=read('three-view.json'),read('seed-1709.json'),read('paired.json')
    for name,wanted in [('sum-bits',4588),('dot-product',3805),('gemm-bias-relu',9561),('stable-argmax',4912)]:
        for rows in (a,b):
            item=rows[name+'/seal3xlearned-2-only'];counts=item['counts']
            assert item['exact'] and all(item['checks'].values()) and item['sealed_before_verifier']
            assert counts['committed']==item['neural_committed']==wanted
            assert sum(item['by_width'].values())==wanted and '3' in item['by_width']
            assert counts['raw_tuples']==counts['verified_parent_tuples']+counts['raw_parent_rejects']
            assert 0<counts['raw_parent_rejects']<counts['raw_tuples'] and counts['exhausted']==0
            assert len(item['raw_sha256'])==64
            neg=rows[name+'/seal3xmasked-2-assist']
            assert neg['exact'] and neg['counts']['committed']<.01*wanted and neg['raw_sha256']!=item['raw_sha256']
        r=replay[name]
        assert r['native']['neural_committed']==0
        assert r['sealed']['raw_sha256']==a[name+'/seal3xlearned-2-only']['raw_sha256']
        for mode,x in r.items():
            assert x['exact'] and x['raw_replay_equal'] and len(x['ms'])==10
            if mode!='native':
                assert all(len(t['anchors'])>=int(w) and t['inputs'] and t['ordinal']>0 for w,t in x['examples'].items())
    for n in ('sum-bits','dot-product'):
        w=read('untrained.json')[n+'/seal3xrandom-2-assist']
        assert w['exact'] and w['counts']['committed']==w['neural_committed']==0
        c=read('equal-budget-all.json')
        all_=c[n+'/sealall-2-assist'];model=c[n+'/seal3xlearned-2-assist']
        assert all_['neural_committed']==0 and all_['counts']['exhausted']>0
        assert model['counts']['raw_tuples']<all_['counts']['raw_tuples'] and model['counts']['exhausted']==0
    print('Verified both seeds, source checks, full pre-verification batches, controls and disjoint multi-witness provenance.')

if __name__=='__main__':check(Path(__file__).resolve().parent)
