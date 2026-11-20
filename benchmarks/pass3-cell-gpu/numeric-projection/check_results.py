"""Verify frozen structural choices, exact integer semantics and the two independent counterexamples."""
from pathlib import Path
import json


def check(root):
    measured=json.loads((root/'results.json').read_text())
    isolated=json.loads((root/'without-domain-residual.json').read_text())
    for case,(expected,writes) in {'sum-bits':(55,33),'dot-product':(197,161)}.items():
        for seed in (1703,1709):
            key=f'{case}/{seed}';d=measured[key];st=d['structural']['concat'];pr=d['predicted']['concat']
            assert st['total']==expected and st['wrote']==writes and st['noop']==expected-writes
            assert st['admitted']==st['structural_winners']>0
            assert pr['structural_winners']==pr['admitted']+pr['numeric_rejected_and_recovered']==st['admitted']
            assert d['forced-wrong']['concat']['admitted']==0
            assert d['visible-port']['ports'][1]>0
            for v in d.values():
                if 'ms' in v:assert len(v['ms'])==10
            assert isolated[key+'/wrong']['domain_committed']==0 and isolated[key+'/wrong']['first_divergence'] is not None
    x=json.loads((root/'conflict.json').read_text());y=json.loads((root/'precision.json').read_text())
    for arm in x:
        assert sorted(map(tuple,x[arm]['writes']))==[(9,11,9,False),(15,11,11,True)]
        assert sorted(v['visible'] for v in x[arm]['consumer_visible_ports'])==[9,11]
    assert sum(x['wrong-field']['port_counts'][2:])>0
    predicted=y['predicted']['numeric_prediction']
    assert len(set(r[0] for r in predicted))==1 and len(set(r[1] for r in predicted))==2
    print('Verified real typed proposals, integer projection, visible receipts, min conflicts and float precision counterexamples.')


if __name__=='__main__':check(Path(__file__).resolve().parent)
