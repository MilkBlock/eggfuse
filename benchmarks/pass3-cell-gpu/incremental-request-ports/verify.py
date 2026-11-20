"""Source and address checks, measurements and explicit lost union-log control."""
import json,sys
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    studies=checked(folder,('results.json',),('sum-bits','conjugate-gradient','3mm'),raw=False)
    control=checked(folder,('lost-log.json',),('sum-bits',),raw=False)
    for case,arms in [*studies.items(),*control.items()]:
        assert set(arms)=={'vanilla','off','offset','rebuild','delta','union'}|({'lost-log'} if arms is control.get(case) else set())
        off=arms['offset']
        for label,v in arms.items():
            if label in ('off','vanilla','offset'): continue
            for key in ('raw','multi','physical','commits','children'):
                assert v[key]==off[key]
            assert v['patch']['peak_rows']<=65536 and v['patch']['audit_rows']>=v['patch']['built_rows']>0
            assert v['bridge']['requests']==off['bridge']['requests']
            assert v['wake']['active_roots']==off['wake']['active_roots']
        assert arms['union']['patch']['repairs']>0 and arms['union']['patch']['union_repairs']>0
        assert arms['rebuild']['patch']['built_rows']>arms['union']['patch']['built_rows']
    log=control['sum-bits']['lost-log']['patch']
    assert log['union_repairs']==0 and log['stale_logs']>0
    transfer=checked(folder,('deriche.json',),('deriche',),raw=False)['deriche']
    assert set(transfer)=={'vanilla','off','offset','union'}
    a,b=transfer['offset'],transfer['union']
    for k in ('raw','multi','physical','commits','children'):assert a[k]==b[k]
    assert a['bridge']['requests']==b['bridge']['requests']
    assert b['patch']['union_repairs']>0 and b['patch']['built_rows']<a['wake']['index_build_rows']
    phases=json.loads((folder/'phases.json').read_bytes())
    for v in phases.values():
        assert set(v)=={'offset','rebuild','delta','union'}
        for samples in v.values():
            assert len(samples)==3 and all(0<s['directory_ms']<=s['activation_ms']<s['inference_ms'] for s in samples)
    fixture=json.loads((folder/'fixture.json').read_bytes())
    for name,row in fixture.items():
        assert [bool(s) for s in row['source']['unions']]==[False,False,False,False,False,True,False]
        assert [w['run'] for w in row['winners']]==[1,3,5,7]
        for key in ('source','state','raw','cells','winners'):assert row[key]==fixture['direct'][key]
    assert fixture['patch']['wake']['direct_receipts']==fixture['patch']['wake']['audited_receipts']==3
    return {**studies,'deriche':transfer}

if __name__=='__main__':print('Verified stable learned subscriptions, union repairs, lost history, native timings and staged fixture on',len(verify(HERE)),'Pass 3 programs')
