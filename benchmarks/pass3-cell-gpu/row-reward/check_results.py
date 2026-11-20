from pathlib import Path
import json


def check(root):
    rows=json.loads((root/'results.json').read_bytes());c=json.loads((root/'calibration.json').read_bytes())
    assert len(rows)==8 and len(c['programs'])==4 and len(c['net_us'])==7
    for key,arms in rows.items():
        for arm in ('supervised','team','weighted','weighted_cf'):
            v=arms[arm]
            assert v['aligned'] and v['without_residual']['first_divergence']==1
            assert v['exact']+v['neural']==v['rhs'] and sum(v['by_row'])==v['neural'] and v['duplicates']==0
            assert len(v['ms'])==len(v['cli_ms'])==10
    print('Checked native row-reward attribution, held-out source conformance, timing and calibration split.')


if __name__=='__main__':check(Path(__file__).resolve().parent)
