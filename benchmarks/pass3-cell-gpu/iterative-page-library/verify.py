import json,sys
from pathlib import Path
from train import CASES,ranking
from policy import deploy
from evaluate_returns import returns
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    read=lambda f: json.loads((folder/f).read_bytes())
    learned=read('learning.json');p=learned['policies']
    assert tuple(learned['training'])==CASES and set(learned['round1'])==set(learned['round2'])==set(CASES)
    a=ranking(learned['round1']);b=ranking(learned['round2'])
    assert p['first']['members']==a[:8] and p['one-pass']['members']==a[:16]
    assert p['iterated']['members']==a[:8]+b[:8] and not set(a[:8])&set(b)
    assert len(learned['features'])==learned['universe']
    rows=list(learned['features'].items())
    for n,v in p.items():
        if 'weights' in v:
            assert v['params'] in (9,81) and set(deploy(rows,v))==set(v['members'])
    for round_name in ('round1','round2'):
        for data in learned[round_name].values():
            for k,v in data.items():
                assert v['x']==learned['features'][k] and v['calls']>0 and len(v['expanded'])==len(v['original'])==5
    test=checked(folder,('results.json',),('conjugate-gradient','3mm'))
    repeat=checked(folder,('seed1709.json',),('conjugate-gradient',))
    for grp in (test,repeat):
        for arms in grp.values():
            assert arms['all']['library']['selected']==arms['all']['library']['invocations']>0
            for k,r in arms.items():
                if k in ('vanilla','off','all'):continue
                assert r['library']['invocations']==arms['all']['library']['invocations']
                assert 0<=r['library']['selected']<=r['library']['invocations']
    assert read('weighted.json')==returns(read('heldout-costs.json'),p)
    unseen=read('unseen.json')
    assert unseen['all']['unknown']>0 and unseen['all']['calls']['selected']>0
    for r in unseen.values():
        for f in ('cells','raw','graph','source_rhs'):assert r[f]==unseen['off'][f]
    return test

if __name__=='__main__':print('Verified two training passes, frozen table and return heads, held-out source and physical credit, and unseen source layout on',len(verify(HERE)),'held-out Pass 3 programs')
