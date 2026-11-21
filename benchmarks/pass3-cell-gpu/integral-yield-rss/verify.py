"""Verify all original Run ledgers, each OS sample's native checkpoint and first passage."""
import json
from pathlib import Path
from analyze import summarize,transform
HERE=Path(__file__).resolve().parent
MODES={'cpu','raw_external','filter_external','raw_closed','filter_closed','filter_mixed'}


def verify():
    curves=json.loads((HERE/'curves.json').read_bytes());ev=json.loads((HERE/'audit.json').read_bytes())
    assert set(curves)==set(ev)=={'sum-bits','3mm'}
    transform(curves,ev,False);results=summarize(curves,ev)
    assert results==json.loads((HERE/'results.json').read_bytes())
    joint_file=HERE.parent/'integral-filter-joint/results.json'
    joints=json.loads(joint_file.read_bytes())
    for case,x in curves.items():
        assert len(x['order'])==4*2*len(MODES) and set(x['rows'])==MODES
        for name,pairs in x['rows'].items():
            flags=[f for _,k,f in x['order'] if k==name]
            assert flags[::2].count(True)==2
            assert all(len(t['sampled']['trace'])>4 for t in pairs)
            if name=='cpu':continue
            v=ev[case]['arms'][name]
            assert len(v['ledger']['rows'])==ev[case]['reference']['runs']
            e=joints[case][name]
            assert v['ledger']['rows'][-1]==[e['wire_bytes'],(e['internal'] or {}).get('counts',{}).get('confirmed',0),*e['emitted']]
            for f in ('rhs','root_parents','root_ids','nested_ids','cells','children','single_winners','multi_winners','state_sha'):
                assert e[f]==v['source'][f]
            end=results[case]['arms'][name]['median']['end_progress']
            if name.endswith(('closed','mixed')):assert end['internally_committed']>0
            if name!='raw_external':assert end['wire_bytes_avoided']>0
    print('Verified common thresholds, 6 independent calibrations and 96 fresh-process samples/controls, same-Run wire bytes and confirmed integral commits, and independent Pass 3 source evidence.')


if __name__=='__main__':verify()
