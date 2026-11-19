"""CPU-only binding and equivariance replay of the 64 saved panel traces."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
from data import audit
from study import panels,input_digest


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    r=json.loads((a.root/'results.json').read_text());suite,maps=panels();checked=0
    for name,(_,length,ports,data) in suite.items():
        assert input_digest(data)==r['panel_hashes'][name]
        for model,snapshot in r['reports'][name].items():
            path=a.root/'traces'/f'{name}-{model}.npz'
            with np.load(path,allow_pickle=False) as z:
                reference=audit(data,*(z[k] for k in ('ptr1','ptr2','pair_origin','pair_value','result_value')))
                assert snapshot['whole_graphs']==reference['whole_graphs']
                for stage in ('run1','run2'):
                    assert all(snapshot[stage][k]==v for k,v in reference[stage].items())
                if name in maps:
                    base,layout=maps[name];g=np.arange(len(layout))[:,None]
                    with np.load(a.root/'traces'/f'{base}-{model}.npz') as old:
                        for field in ('ptr1','ptr2'):
                            # Reverse both index changes to recover the original target.
                            mapped=np.argsort(layout,axis=1)[g,z[field][g,layout]]
                            exact=(mapped==old[field])
                            report=r['relayout'][name][model]
                            assert int(exact.sum())==report[field+'_equal'] and int(exact.all(-1).sum())==report[field+'_exact_graphs']
                checked+=len(z['ptr1'])
    assert 'torch' not in sys.modules
    print(json.dumps(dict(panel_traces=sum(len(d) for d in r['reports'].values()),graph_evaluations=checked,source_audit_and_relayout='pass')))


if __name__=='__main__':main()
