"""Trace ceiling for SINGLE leaves. Count each reference winner once at its original Run."""
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np


def summarize(capture):
    with np.load(capture/'training.npz') as z,np.load(capture/'output.npz') as graph:
        gold=z['positive'].sum(1);valid=(z['receipt']==1).sum(1)
        rhs=graph['runs'][:,1]
    assert len(gold)==len(rhs) and np.all(gold<=valid) and np.all(gold<=rhs)
    return dict(rhs=int(rhs.sum()),runs=len(rhs),windows_with_winner=int((gold>0).sum()),
                winners_at_any_budget=int(gold.sum()),successful_candidate_positions=int(valid.sum()),
                max_winners_in_one_run=int(gold.max()),winner_histogram=dict(sorted(Counter(map(int,gold)).items())),
                budgets={w:dict(reference_winners=int(np.minimum(gold,2*w).sum()),
                                successful_positions=int(np.minimum(valid,2*w).sum())) for w in (1,2,4,8,16,32)})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args()
    records={name:summarize(a.capture/name) for name in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax')}
    a.output.write_text(json.dumps(records,indent=1)+'\n')
