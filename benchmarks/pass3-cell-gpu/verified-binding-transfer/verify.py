"""Check source ledgers and physical Cell IDs separately from timing or resident memory."""
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked

def verify(folder):
    data=checked(folder,['results.json'],['sum-bits','3mm'])
    for case,arms in data.items():
        assert set(arms)=={'vanilla','off','move','receipt','run-tickets','all'}
        source=arms['off']
        for name,v in arms.items():
            assert len(v['ms'])==4
            if name=='vanilla':continue
            s=v['transfer']
            moved=name in ('all','move')
            reused=name in ('all','receipt')
            scoped=name in ('all','run-tickets')
            assert (s['projected_marks_moved']>0)==moved and (s['winning_marks_moved']>0)==moved
            assert (s['receipt_rows']>0)==reused and (s['receipt_fields']>0)==reused
            assert s['corrupt_controls']==int(reused)
            assert (v['ticket_retired']>0)==scoped and (v['ticket_peak']<source['ticket_peak'])==scoped
            assert v['ticket_peak']>0 and v['counts']['exhausted']==0
        for name in ('move','receipt','run-tickets'):
            key={'move':'winning_marks_moved','receipt':'receipt_fields'}.get(name)
            if key:assert arms['all']['transfer'][key]==arms[name]['transfer'][key]
        assert arms['all']['ticket_peak']==arms['run-tickets']['ticket_peak']
    return data

if __name__=='__main__':print('Verified source/winner orders, physical roots, slot corruption and ticket lifetime for',len(verify(HERE)),'complete programs.')
