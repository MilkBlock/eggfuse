import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import CASES,checked

def verify(folder):
    data=checked(folder,('anchors.json','transfer.json'),CASES)
    for case,arms in data.items():
        for arm,row in arms.items():
            if arm=='vanilla':continue
            assert row['clock_ns']>0 and row['order']['time_ns']==0
            if arm!='source':assert row['order']['matched_layouts']>0
            if arm=='prefix':assert row['order']['prefixed_batches']>0
    return data

if __name__=='__main__':print('Verified stable binding identity, order and measured ordering work:',len(verify(HERE)),'programs')
