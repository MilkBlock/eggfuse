import json
from pathlib import Path


def check(root):
    read=lambda name:json.loads((root/name).read_text())
    data=read('results.json');wake=read('wake-results.json');algebra=read('algebra-results.json')
    assert len(data)==16
    for case,v in data.items():
        assert len(v['arms'])==6
        for arm,record in v['arms'].items():
            failure=case=='no-merge' or (v['stress'] and v['stress'][0]>63 and arm.startswith('mask-'))
            assert (record['status']=='expected_failure')==bool(failure)
            if failure:continue
            assert record['logical_endpoints'] and record['runs']==v['source']['runs']
            assert len(record['ms']) in (4,6) and record['memory']['peak_heap']>=record['memory']['completion_heap']
            if case in ('full','full-probes'):
                assert record['runs']==835 and record['rhs']==(382 if case=='full' else 390)
            if case=='full-probes':
                assert [record['measurements'][k] for k in ('insert','intersect','union','length')]==[1,2,2,3]
            if case=='dynamic':assert wake[case][arm]['same_key_two_to_one']==1
            if v['stress']:assert record['cardinality']==[v['stress'][1]-1]
        if case in wake:assert len({e['actual_set_rows_woken'] for e in wake[case].values()})==1
    for arm,v in algebra.items():
        if not arm.startswith('mask'):assert v['observed']=={'Before':[4,1,1,3],'After':[3,2,0,3]}
    print('Verified native Set storage, capacities, source schedule, cross-segment operations and union notifications.')


if __name__=='__main__':check(Path(__file__).resolve().parent)
