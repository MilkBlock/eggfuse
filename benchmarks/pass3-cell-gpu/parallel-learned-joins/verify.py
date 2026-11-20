"""Recheck full source identities and measured worker execution in the admitted shape family."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent


def verify(name):
    data=json.loads((HERE/name).read_bytes())
    for case,case_data in data.items():
        arms=case_data['arms'];ref=arms['original']['identity']
        for label,a in arms.items():
            assert len(a['ms'])==6
            if label=='vanilla':
                assert a['rhs']==ref['rhs'] and a['graph']==ref['state_sha']
                continue
            assert a['aligned'] and a['identity']==ref and ref['direct_cells']*100>=98*a['fresh']
            if label=='original':continue
            s=a['audit'];assert 0<s['raw']<=ref['published'] and s['attempts']>=s['raw']
            assert s['peak_workers'] and s['peak_overlap'] and not s['speculative']
            assert len(a['samples'])==6
            if label in ('2','4','cached2','cached4'):
                assert s['peak_workers']>1 and s['peak_overlap']>1 and s['multicore_calls']>0
            if label in ('local','cached1','cached2','cached4'):
                assert s['epoch_hits'] and s['bucket_hits'] and 0<s['peak_retained']<=4<<20
        for i,message in [('1','invalid learned worker frame generation'),('2','invalid learned worker result offset')]:
            if case in ('sum-bits','dot-product'):assert case_data['faults'][i]['error']==message
    print('Checked',name,'publication order, exact RHS, physical coverage and measured worker activity.')


if __name__=='__main__':
    verify('packed.json')
    verify('resident.json')
