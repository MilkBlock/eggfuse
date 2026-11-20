import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import CASES,checked

def verify(folder):
    rows=checked(folder,('anchors.json','transfer.json'),CASES)
    for case,arms in rows.items():
        for name in ('move','edit'):
            s=arms[name]['edits']
            assert s['retained_without_clone'] and s['checked_source_rows']>=s['retained_without_clone']
        assert arms['edit']['edits']['in_place']>0
        if 'held-reader' in arms:assert arms['held-reader']['edits']['copy_fallback']>0 and arms['held-reader']['edits']['updates']==0
    return rows

if __name__=='__main__':print('Checked immutable source frames:',len(verify(HERE)),'programs')
