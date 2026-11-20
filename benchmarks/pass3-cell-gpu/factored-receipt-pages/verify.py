import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked

def verify(folder):
    data=checked(folder,('results.json',),('sum-bits','conjugate-gradient','3mm'))
    original={}
    for filename in ('core.json','large.json'):
        original.update(json.loads((folder.parent/'composed-cpu'/filename).read_bytes()))
    for name,arms in data.items():
        assert set(arms)=={'vanilla','off','direct','dictionary','selective','stream'}
        off=arms['off']
        old=original[name]['combined-lazy']
        for k in ('raw','multi','wire_hash','state_sha','single_winners','multi_winners','cells','direct_cells','physical','commits','children','root_parents','root_ids','nested_ids'):
            assert off[k]==old[k]
        for label,row in arms.items():
            if label=='vanilla':continue
            p=row['page']
            assert p['canonical_wire_bytes']==p['audited_wire_bytes']>0 and p['encoded_wire_hash']!=0
            assert p['pages']>0 and p['refs']==row['counts']['raw_root_slots']
            assert p['body_bytes']<p['retained_bytes']
            if label=='off':
                assert p['flat_transfer_bytes']==p['body_bytes']
                assert p['canonical_wire_bytes']==p['body_bytes']+72*p['pages']
                continue
            assert p['pages']==p['packed_pages'] and p['flat_pages']==0
            assert p['checked_refs']==p['refs'] and p['coordinate_faults']==0
            assert p['word_bytes']+p['lane_bytes']+p['role_bytes']==p['body_bytes']
            assert p['canonical_wire_bytes']==72*p['pages']+18*(p['dictionary_roles']+p['direct_roles'])+p['word_bytes']+p['lane_bytes']
            for field in ('wire_bytes','wire_hash','emitted','rejected','root_allocated','direct_cells'):
                assert row[field]==off[field]
        direct,forced,selective,stream=[arms[k]['page'] for k in ('direct','dictionary','selective','stream')]
        assert direct['word_bytes']==direct['refs']*16 and direct['dictionary_roles']==0
        assert forced['direct_roles']==0 and 0<forced['word_bytes']<direct['word_bytes']
        assert selective['canonical_wire_bytes']<=min(direct['canonical_wire_bytes'],forced['canonical_wire_bytes'])
        assert stream['pages']==stream['streamed_pages']
        assert stream==dict(selective,streamed_pages=stream['streamed_pages'])
    assert 'invalid encoded parent coordinate' in data['sum-bits']['off']['invalid_coordinate']['failure']
    assert set(data['sum-bits']['off']['source_faults'])=={'1','2','3'}
    return data

if __name__=='__main__':
    print('Verified decoded multi-parent coordinates, exact wire/physical certificates, fault controls and source-aligned timings on',len(verify(HERE)),'workloads')
