"""Verify all private Cell controls and the independent frozen source/physical ledgers."""
import argparse,json
from pathlib import Path
HERE=Path(__file__).resolve().parent


def verify(folder):
    data=json.loads((folder/'controls.json').read_bytes())
    assert set(data)=={'sum-bits','dot-product'}
    for name,arms in data.items():
        assert set(arms)=={'off','zero','over','stale','withheld'}|{f'{t}/{s}' for t in ('run','page') for s in ('capacity','pooled','named')}
        original=arms['off']
        assert original['aligned'] and all(original['checks'].values()) and original['rhs']==original['neural_rhs']
        for arm,v in arms.items():
            for k in ('single_winners','multi_winners','cells','state_sha','root_parents','root_ids','nested_ids',
                      'rhs','direct_cells','raw','multi','physical','commits','children'):
                assert v[k]==original[k]
            assert v['aligned'] and all(v['checks'].values())
            if arm=='off':continue
            c=v['counters'];assert c['fresh']==v['root_allocated'] and c['committed']==v['applied']
            assert c['used']+c['fallback']==c['fresh'] and c['used']+c['unused']==c['granted']
            assert c['preconstructed']+c['capacity_only']==c['granted']==c['requested']-c['clipped']
            assert c['used']==c['direct_fresh']+c['promoted']
            if arm in ('zero','withheld','stale'):
                assert c['used']==0
            elif arm.endswith('/capacity'):
                assert c['preconstructed']==c['sampled_payloads']==c['payload_identity']==0
                assert c['used']>0 and c['capacity_only']>0
            else:
                assert 0<c['used']==c['sampled_payloads']==c['payload_identity'] and c['capacity_only']==0
            if '/' in arm:
                assert 0<c['peak_slots']<=37 and v['samples']>0
                assert c['stale_named']==c['missing_named']==c['parent_mismatch']==0
            if arm.endswith('/named'):assert c['names_attached']>=c['used']
        assert arms['withheld']['counters']['missing_named']>0 and arms['stale']['counters']['stale_named']>0
        assert arms['zero']['counters']['granted']==0 and arms['over']['counters']['unused']>0
    return data


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path,nargs='?',default=HERE)
    print('Verified private reservations, matched named source receipts, physical payload identity and independent source schedules on',len(verify(p.parse_args().folder)),'programs')
