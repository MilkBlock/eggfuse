"""Replay ordered min receipts to bound request reuse without collapsing observable writes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import numpy as np


def replay(outcomes, operands, width, only=None):
    stats = Counter()
    key_state = {}
    scalar_state = {}
    cohort = None
    occupied = 0
    for i, row in enumerate(outcomes):
        run, rule, had, old, candidate, visible, changed, token, _, _, table, _, _, key = map(int, row[:14])
        if not run or not token or (only is not None and rule != only):
            cohort = None
            continue
        if (run, rule) != cohort or occupied == width:
            cohort = (run,rule)
            occupied = 0
            key_state.clear()
            scalar_state.clear()
            stats['batches'] += 1
        occupied += 1
        stats['rhs'] += 1
        # In this corpus the typed numeric compiler accepts at most four i64 source operands.
        # Unused operands are zero initialized; entries 4 and 5 are model predictions/metadata.
        args = tuple(map(int, operands[token - 1,:4]))
        if args in scalar_state:
            assert scalar_state[args] == candidate, (i,run,rule,args)
            stats['repeated_scalar_inputs'] += 1
        scalar_state[args] = candidate
        target = (table,key)
        if target in key_state:
            assert had and key_state[target] == old, (i,run,rule,key)
            stats['repeated_write_keys'] += 1
        landed = min(candidate,old) if had else candidate
        assert landed == visible and changed == (not had or landed != old)
        key_state[target] = landed
        stats['writes'] += changed
        stats['candidate_differs_from_visible'] += int(candidate != visible)
    return {k:stats[k] for k in ('batches','rhs','repeated_scalar_inputs','repeated_write_keys','writes','candidate_differs_from_visible')}


def main(source):
    out = {}
    for case in ('sum-bits','dot-product'):
        for seed in (1703,1709):
            path=source/f'{case}-{seed}-structural'/'numeric.npz'
            with np.load(path) as z:
                out[f'{case}/{seed}'] = dict(
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    source_rhs=int(len(z['outcomes'])),
                    numeric_outcomes=int((z['outcomes'][:,0]!=0).sum()),
                    all={n:replay(z['outcomes'],z['args'],n) for n in (1,8,32)},
                    concat={n:replay(z['outcomes'],z['args'],n,154) for n in (1,8,32)},
                )
    return out


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('out',type=Path)
    args=p.parse_args();args.out.write_text(json.dumps(main(args.source),indent=1)+'\n')
