from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    groups=checked(folder,('results.json',),('sum-bits','conjugate-gradient','3mm'))
    for name,arms in groups.items():
        assert set(arms)=={'vanilla','off','prepared','register','register-key','port'}
        base=arms['register']
        for arm in ('register','register-key','port'):
            q=arms[arm];s=q['block']
            assert s['started']==s['completed']+s['stale']+s['key_misses']+s['guard_failures']
            assert s['completed']==q['counts']['validated']>0
            for k in ('started','completed','stale','key_misses','guard_failures','value_slots'):
                assert s[k]==base['block'][k]
            assert q['page']['audited']==q['counts']['raw_tuples']
        w=arms['port']['block']
        assert 0<w['parent_port_hits']==base['source_points']-arms['port']['source_points']
        assert w['avoided_key_fields']>0 and w['peak_ports']<=4096
    return groups

if __name__=='__main__':print('Verified the compiled suffix, per-parent port results and original source and Cell endpoints on',len(verify(HERE)),'complete programs')
