"""Verify source and raw-stream equivalence, page-scoped work and interleaved timings."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked


def verify(folder):
    groups=checked(folder,('core.json','large.json'),('sum-bits','conjugate-gradient','3mm','deriche'))
    for case,arms in groups.items():
        ref=arms['check']['page']
        for mode,q in arms.items():
            if mode in ('off','vanilla'):continue
            s=q['page']
            assert s['tuples']==s['audited']==ref['tuples']==q['counts']['raw_tuples']
            assert s['accepted_parent_sets']==ref['accepted_parent_sets']
            assert s['logical_parents']==s['source_reads']+s['row_hits']
            assert s['peak_rows']<=8192 and s['peak_points']<=4096
            if mode in ('rows','shared','block'):assert s['row_hits']>=s['later_role_hits']>0
            if mode in ('points','block'):
                assert s['suffix_requests']==s['suffix_hits']+s['suffix_reads']
                assert s['suffix_hits']>0 and arms['off']['source_points']-q['source_points']==s['suffix_hits']
        assert not ref['row_hits'] and arms['block']['page']['projected_slots']>0
    return groups

if __name__=='__main__':print('Verified all sealed proposals, source winners, work counters and physical Cells on',len(verify(HERE)),'Pass 3 programs')
