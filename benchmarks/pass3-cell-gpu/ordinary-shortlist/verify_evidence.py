"""Check that changing learned shortlist storage or lifetime preserved the complete raw batch."""
import json
from pathlib import Path

def verify(path):
    for f,reps in [('results.json',10),('flat.json',12),('seed1709.json',4)]:
        results=json.loads((path/f).read_bytes())
        for case,n in [('sum-bits',4588),('dot-product',3805),('gemm-bias-relu',9561),('stable-argmax',4912)]:
            r=results[case]
            for key,v in r.items():
                assert v['exact'] and len(v['ms'])==reps and v['counts']['exhausted']==0
                if key=='native':assert v['neural_committed']==0;continue
                assert v['neural_committed']==n
                orig=v['raw_and_winners_equal_to']
                if orig:
                    assert v['raw_sha256']==r[orig]['raw_sha256'] and v['counts']['raw_tuples']==r[orig]['counts']['raw_tuples']
            assert r['stack']['counts']['score_bucket_reads']<r['three']['counts']['score_bucket_reads']
            assert r['stack']['shortlist']['hits_across_runs']>0
            if 'epoch' in r:assert r['epoch']['shortlist']['hits_across_runs']==0
            if 'flat' in r:
                assert r['flat']['shortlist']['snapshot_row_reads']>0 and r['flat']['shortlist']['offset_rejects']==0
    negative=json.loads((path/'hint-controls.json').read_bytes())
    for case in ('sum-bits','dot-product'):
        base=negative[f'{case}/flatseal3xlearned-2-assist']
        for mode,field in [('badpos','offset_rejects'),('badgen','generation_rejects')]:
            v=negative[f'{case}/{mode}flatseal3xlearned-2-assist']
            assert v['exact'] and v['raw_sha256']==base['raw_sha256']
            assert v['neural_committed']==0 and v['shortlist'][field]==v['counts']['raw_tuples']>0
    print('Verified exact candidate streams, ordinal equivalence, table-version cache lifetimes and rejected source hints.')
if __name__=='__main__':verify(Path(__file__).resolve().parent)
