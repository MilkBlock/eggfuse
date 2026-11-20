import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import CASES,checked


def verify(folder):
    data=checked(folder,('anchors.json','transfer.json'),CASES,raw=False)
    for case,arms in data.items():
        baseline=arms['eager']
        for arm,row in arms.items():
            if arm in ('vanilla','off'):continue
            for key in ('raw','multi','commits','physical','children'):
                assert row[key]==baseline[key],(case,arm,key)
            if arm!='eager':
                assert row['lazy']['checks']>0
            if arm=='memo':
                assert row['lazy']['computed']>0 and row['lazy']['table_hits']>0
                assert row['lazy']['fallback']==0
        assert arms['memo']['counts']['raw_tuples']<arms['off']['counts']['raw_tuples']
    return data

if __name__=='__main__':print('Verified the same finite arithmetic projection at different execution times on',len(verify(HERE)),'source programs.')
