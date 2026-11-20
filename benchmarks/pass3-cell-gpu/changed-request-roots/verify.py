from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    groups=checked(folder,('core.json','large.json'),('sum-bits','conjugate-gradient','3mm','deriche'),raw=False)
    for name,arms in groups.items():
        assert set(arms)=={'off','vanilla','direct','target','receipt','presence'}|({'point'} if name in ('sum-bits','conjugate-gradient') else set())
        ref=arms['direct']
        for mode,row in arms.items():
            if mode in ('off','direct','vanilla'):continue
            for f in ('raw','multi','commits','physical','children'):
                assert row[f]==ref[f]
            wake=row['wake']
            assert wake['routed_calls'] and 0<wake['peak_rows']<=65536
            assert 0<wake['all_roots']-wake['active_roots']==ref['bridge']['root_rows']-row['bridge']['root_rows']
            assert row['bridge']['requests']<ref['bridge']['requests']
            assert wake['audited_receipts']==wake['direct_receipts']
        assert arms['target']['bridge']['requests']-arms['receipt']['bridge']['requests']==arms['receipt']['wake']['direct_receipts']>0
        assert arms['target']['bridge']['root_rows']==arms['receipt']['bridge']['root_rows']
    return groups

if __name__=='__main__':
    print('Verified changed request activation, raw sealed streams and physical winners across',len(verify(HERE)),'programs')
