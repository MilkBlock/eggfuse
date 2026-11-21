from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked
def verify(folder):
    groups=checked(folder,('results.json',),('sum-bits','conjugate-gradient','3mm'))
    for case,r in groups.items():
        assert set(r)=={'vanilla','off','coordinates','pass','buffer'}
        for k in ('pass','buffer'):
            w=r[k]['handoff']
            assert w['checked_page_slots']==w['accepted']>0
            assert w['parent_headers_saved']+w['projected_headers_saved']==w['audit_headers']==r['coordinates']['root_header_checks']-r[k]['root_header_checks']
        assert r['pass']['handoff']['exact_buffers']==0 and r['buffer']['handoff']['exact_buffers']>0
    assert set(groups['sum-bits']['off']['faults'])=={'lane','1','2','3'}
    return groups
if __name__=='__main__':print('Verified same-page physical transfer, corrupted roots and exact endpoints on',len(verify(HERE)),'programs')
