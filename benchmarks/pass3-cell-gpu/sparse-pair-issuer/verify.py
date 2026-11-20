import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import CASES,checked

def verify(folder):
    rows=checked(folder,('anchors.json','transfer.json'),CASES)
    for case,arms in rows.items():
        for name,row in arms.items():
            if name in ('vanilla','off'):continue
            s=row['sparse']
            assert s['unneeded_epoch_sorts']>0
            if name!='epochs':assert s['admitted']>0 and s['age_tests']==s['right_rows']
    return rows

if __name__=='__main__':print('Verified delta-pair source order:',len(verify(HERE)),'programs')
