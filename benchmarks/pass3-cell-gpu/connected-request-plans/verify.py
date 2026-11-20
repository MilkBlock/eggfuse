"""Independently replay the source-side planning and verify the online provenance."""
from pathlib import Path
import json
import sys
from lower import lower,validate

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    survey=json.loads((folder/'census.json').read_bytes())
    found=survey['reduced']
    assert (survey['plans'],survey['width_gap'],len(found))==(341,107,64)
    for rid,v in found.items():
        rule={'query':v['atoms']}
        order=lower(rule)
        assert [list(item) for item in order]==v['order']
        assert v['lower_bound'] <= validate(rule,order)==v['connected'] < v['original']
    # The source contract permits forward full-key requests. An inverse call
    # would make two unrelated source rows seem connected.
    def atom(name,*args):
        return dict(call={'table':name},args=[{'slot':s} for s in args])
    two={'query':[atom('Source',0,1),atom('Read',1,2),atom('Target',2,3,4)]}
    order=lower(two)
    assert order==[('pick',0),('request',1),('pick',2)] and validate(two,order)==2
    assert lower({'query':[atom('A',0,1),atom('B',2,3)]}) is None
    case='507'
    assert found[case]['order']==[['pick',3],['request',1],['pick',0],['suffix',2]]
    profiles=json.loads((HERE.parent/'pair-source-frontier/profile.json').read_bytes())
    for name,row in survey['workloads'].items():
        observations=[p for i,p in profiles[name]['rules'].items() if i in found]
        assert row['prior_raw']==sum(p['raw'] for p in observations)
        assert row['prior_root_visits']==sum(p['root_visits'] for p in observations)

    cases=checked(folder,('results.json',),('sum-bits','conjugate-gradient','3mm','deriche'),raw=False)
    for name,arms in cases.items():
        assert set(arms)=={'vanilla','off','request','memo'}
        a,b=arms['request'],arms['memo']
        assert a['raw']==b['raw'] and a['counts']['raw_tuples']==b['counts']['raw_tuples']
        for r in (a,b):
            w=r['bridge']
            assert w['calls']>0 and w['found']>0 and w['raw']>0
            assert w['raw']==sum(v[1] for v in w['active'].values())
            assert w['calls']==sum(v[0] for v in w['active'].values())
        assert b['bridge']['requests']+b['bridge']['cached']==a['bridge']['requests']
        assert b['bridge']['found']==a['bridge']['found']
    extra=checked(folder,('directory.json',),('conjugate-gradient','3mm'),raw=False)
    for name,arms in extra.items():
        assert set(arms)=={'vanilla','off','request','memo','directory'}
        d=arms['directory'];a=arms['request'];stats=d['bridge']
        assert d['raw']==a['raw']==arms['memo']['raw']
        assert stats['directory_reads']==stats['audited_directory_reads']>0
        assert stats['requests']+stats['directory_reads']==a['bridge']['requests']
        assert stats['directory_rows']>0 and stats['directory_reuses']>0
        assert stats['found']==a['bridge']['found'] and stats['score_visits']==a['bridge']['score_visits']
    assert cases['sum-bits']['off']['finite_control_original_digest']==cases['sum-bits']['off']['raw']
    assert extra['conjugate-gradient']['off']['finite_control_original_digest']==extra['conjugate-gradient']['off']['raw']
    return cases


if __name__=='__main__':
    print('Verified compiled request order, actual issuance, winning source and physical Cell ownership on',len(verify(HERE)),'programs')
