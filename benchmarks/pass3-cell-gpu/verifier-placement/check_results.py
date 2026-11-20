import json
from pathlib import Path


def verify(root):
    prefix=json.loads((root/'prefix.json').read_bytes())
    assert prefix['cpu_verifier']=='Rust cell-proof-verifier' and prefix['repeats']==24
    assert len(prefix['samples'])==4
    for row in prefix['samples'].values():
        assert set(row['placements'])=={'cpu1/cpu','mps/cpu','mps/mps'}
        assert row['illegal']==row['uncovered']==0 and row['all_fields_identical']
        assert set(row['controls']['missing'])=={0,1}
        for arm in row['placements'].values():assert len(arm['both_us'])==24
    tx=json.loads((root/'transactions.json').read_bytes())
    for name,row in tx.items():
        assert row['static']+row['dynamic']==row['events']==row['invalidated_stale']
        assert row['rule_pairs']==[['SubTuple',2,1,137,138]]
        assert row['dynamic_neural_roots']==0 and row['observed_neural_roots']>0
        assert row['corrected_branches']==row['prior_errors']>0
        assert row['epoch_batches']<row['dynamic'] and set(row['ms'])=={'blind','deferred','epoch','individual'}
        assert all(len(trials)==9 for trials in row['ms'].values())
    print('Verified the three requested placements, versioned i64 transactions and source/neural cohorts.')


if __name__=='__main__':verify(Path(__file__).resolve().parent)
