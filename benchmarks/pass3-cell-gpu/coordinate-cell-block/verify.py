import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    groups=checked(folder,('results.json',),('sum-bits','conjugate-gradient','3mm'))
    for case,arms in groups.items():
        assert arms['off']['fault']['partial_rhs']<arms['vanilla']['rhs']
        for name,q in arms.items():
            if name in ('off','encoded','hash-block','vanilla'):continue
            s=q['words']
            assert s['pages']>0 and 0<s['loaded']<=s['words']<=s['lanes']
            assert s['audited']==q['counts']['raw_tuples'] and s['cap_fallbacks']==0
            b=q['block'];old=arms['hash-block']['block']
            for key in ('started','completed','stale','key_misses','guard_failures','value_slots'):
                assert b[key]==old[key]
            if name in ('words','eager','ports'):
                assert b['parent_port_hits']==old['parent_port_hits']
            if name!='words':assert s['port_maps']>0
    f=json.loads((folder/'fixture.json').read_bytes())
    assert set(f)=={'source','hashed','direct'}
    for row in f.values():
        assert any(row['source']['unions'])
        for k in ('graph','cells','source','winners','raw'):assert row[k]==f['source'][k]
    assert 'coordinate' in f['direct']['fault'] and f['direct']['words']['audited']>0
    return groups

if __name__=='__main__':print('Verified coordinate-selected Cell blocks, negative control and independently audited complete source executions on',len(verify(HERE)),'Pass 3 workloads')
