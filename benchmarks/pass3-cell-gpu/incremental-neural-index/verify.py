"""Check the measured invariants of the incremental learned source-admission arms."""
import argparse
import json
from pathlib import Path
from statistics import median


def check(folder):
    def read(name):return json.loads((folder/(name+'.json')).read_text())
    for name,number in [('memo',8),('two-parents',8),('deltas',6),('freshness',8)]:
        for case,arms in read(name).items():
            original=arms['stackseal3xlearned']['audit']
            for mode,item in arms.items():
                assert len(item['ms'])==number and median(item['ms'])==item['median_ms']
                if mode=='exact':continue
                actual=item['audit'];assert actual['source_exact'] and actual['neural_rhs']==actual['rhs']
                assert actual['allocation_sha']==original['allocation_sha'] and actual['direct_distinct']==original['direct_distinct']
                if 'guard' not in mode:
                    assert all(actual[k]==original[k] for k in ('root_proposal_hash','multi_raw_hash','merge_gate_hash','root_allocations_sha','root_commits_sha'))
                if mode.startswith('rowdelta'):assert item['delta']['applied']>0 and item['delta']['audit_comparisons']>0
                if mode.startswith('tuplememo'):assert item['raw_cache']['reused_tuples']>0
    for name in ('codebook','conjugate','baked','correlated'):
        for case,arms in read(name).items():
            vanilla=arms['vanilla']
            base=next(v for m,v in arms.items() if m.startswith('stackseal'))
            for mode,v in arms.items():
                assert median(v['ms'])==v['median_ms'] and len(v['ms']) in (4,6)
                if mode=='vanilla':continue
                assert all(v['checks'].values()) and v['aligned']
                assert v['rhs']==v['neural_rhs']==vanilla['rhs']
                assert v['state_sha']==base['state_sha'] and v['checks']['state_sha'] and v['fresh']==base['fresh'] and v['cells']==base['cells']
                assert v['direct_cells']==base['direct_cells'] and 100*v['direct_cells']>=98*v['fresh']
                if 'guard' in mode:
                    assert v['counts']['raw_tuples']<base['counts']['raw_tuples']
                else:
                    for k in ('raw','wire_hash','commits','physical','multi','children'):
                        assert v[k]==base[k],(name,case,mode,k)
                # The second generation of the holdout harness explicitly compared the source
                # addresses/ordinals without packet serial numbers, which change when pruning.
                if name!='codebook':
                    for k in ('multi_winners','root_evidence','root_ids','nested_ids'):
                        assert v[k]==base[k],(name,case,mode,k)
    assert set(read('correlated'))=={n+'/1703' for n in ('sum-bits','dot-product','jacobi-1d','conjugate-gradient')}
    print('Verified complete source endpoints and directly constructed Cells, stable permitted tuples, fewer stale proposals and matched median timings.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path,nargs='?',default=Path(__file__).resolve().parent)
    check(parser.parse_args().folder)
