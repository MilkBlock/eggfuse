import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import CASES,checked

def verify(folder):
    rows=checked(folder,('anchors.json','transfer.json'),CASES)
    for case,arms in rows.items():
        for arm,v in arms.items():
            if arm in ('off','vanilla'):continue
            d=v['directory'];assert d['activations']>0 and d['audit_rows']>0
            assert d['peak_charge']<=8<<20
            if arm=='rebuild':assert d['patches']==0
    return rows

if __name__=='__main__':print('Verified rebuilt and versioned learned postings:',len(verify(HERE)),'programs')
