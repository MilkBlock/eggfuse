import json
from pathlib import Path


def check(folder):
    read=lambda name:json.loads((folder/name).read_bytes())
    catalog,growth,results=map(read,('catalog.json','growth.json','results.json'))
    assert catalog['first']==[138,5] and len(catalog['training'])==4
    assert growth['first_round']==[[138,5]] and growth['second_round']==[[138,5],[144,2],[142,2],[140,2]]
    for key,winners,depth in [('sum-bits',90,5),('dot-product',44,6),('gemm-bias-relu',194,10),('stable-argmax',95,7)]:
        for seed in (1703,1709):
            d=results[f'{key}/{seed}'];grown=d['grown-recursive']
            for name,v in d.items():
                assert v['source_exact'] and v['rhs']==v['neural_rhs'] and v['direct']*100>=v['fresh']*98
                if name not in ('shadow','stale'):assert len(v['ms'])==8
            assert grown['winners']==d['grown-flat']['winners']==d['grown-baked']['projected']==winners
            assert d['r1-baked']['winners']<winners and grown['max_chain']==depth
            assert max(grown['counts'][10:14])>0 and not d['stale']['winners'] and not d['shadow']['winners']
    print('Verified train-only guarded growth, native cross-stage source attribution and complete matched graph runs.')


if __name__=='__main__':check(Path(__file__).resolve().parent)
